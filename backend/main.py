

import os
import time
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from dotenv import load_dotenv
from openai import OpenAI
from firecrawl import FirecrawlApp
from ddgs import DDGS
import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
# ----------------------------------------------------------------------------

# Config & keys

# ----------------------------------------------------------------------------

from pathlib import Path

# LOAD ENV
load_dotenv(Path(__file__).parent / ".env")

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Existence checks only — NEVER print secret values.
print("Firecrawl key loaded:", bool(FIRECRAWL_API_KEY))
print("Gemini key loaded:", bool(GEMINI_API_KEY))
print("OpenRouter key loaded:", bool(OPENROUTER_API_KEY))

# Report-generation model.
# NOTE: the free 20B model is a hard quality ceiling for a flagship project.
# Set OPENROUTER_MODEL in .env to a stronger model, or switch generate() to the
# Gemini path shown below.
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-20b:free")

LLM_TIMEOUT = 60            # seconds per LLM call
SCRAPE_TIMEOUT = 25         # seconds per URL scrape
SCRAPE_CHAR_LIMIT = 3000
MAX_URLS = 4
RAG_TOP_K = 4
GEN_TEMPERATURE = 0.3       # low temp -> less drift/hallucination for factual reports
DDG_DELAY_SECONDS = 1       # crude rate-limit cushion (runs in a worker thread)


# ----------------------------------------------------------------------------
# Clients
# ----------------------------------------------------------------------------
openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    timeout=LLM_TIMEOUT,
)

firecrawl = FirecrawlApp(api_key=FIRECRAWL_API_KEY)

embeddings = GoogleGenerativeAIEmbeddings(
    model="models/text-embedding-004",
    google_api_key=GEMINI_API_KEY,
)

# In-memory: collections live for exactly one request, so there's no reason to
# write them to disk or share a mutable directory across uvicorn workers.
chroma_client = chromadb.EphemeralClient()

# All blocking I/O (search, scrape, embed, LLM) gets offloaded here.
executor = ThreadPoolExecutor(max_workers=8)


# ----------------------------------------------------------------------------
# FastAPI app + CORS
# ----------------------------------------------------------------------------
app = FastAPI(title="DeepScout AI")

# Pin explicit origins. allow_origins=["*"] together with allow_credentials=True
# is rejected by browsers and is unsafe. Set ALLOWED_ORIGINS in .env, comma-sep.
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------------------
# Cache (in-memory; use Redis for real multi-worker deployments)
# ----------------------------------------------------------------------------
CACHE = {}
CACHE_EXPIRY = 60 * 30
CACHE_MAX_ENTRIES = 500


def cache_get(key):
    item = CACHE.get(key)
    if not item:
        return None
    if time.time() - item["timestamp"] >= CACHE_EXPIRY:
        CACHE.pop(key, None)
        return None
    return item["data"]


def cache_set(key, data):
    now = time.time()
    # purge expired entries
    for k in [k for k, v in CACHE.items() if now - v["timestamp"] >= CACHE_EXPIRY]:
        CACHE.pop(k, None)
    # cap size (evict oldest)
    if len(CACHE) >= CACHE_MAX_ENTRIES:
        oldest = min(CACHE, key=lambda k: CACHE[k]["timestamp"])
        CACHE.pop(oldest, None)
    CACHE[key] = {"timestamp": now, "data": data}


# ----------------------------------------------------------------------------
# Request models (with validation)
# ----------------------------------------------------------------------------
class ResearchRequest(BaseModel):
    query: str
    history: list = []
    mode: str = "Beginner"

    @field_validator("query")
    @classmethod
    def clean_query(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("query must not be empty")
        return v[:500]


class FollowUpRequest(BaseModel):
    question: str
    report: str
    mode: str = "Beginner"

    @field_validator("question")
    @classmethod
    def clean_question(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("question must not be empty")
        return v[:500]


# ----------------------------------------------------------------------------
# Mode configs
# ----------------------------------------------------------------------------
MODE_CONFIG = {
    "Beginner": {
        "instruction": "Explain in simple language. Use examples and analogies. Avoid heavy jargon.",
        "format": "# Overview\n\n# Simple Explanation\n\n# Easy Example\n\n# Why It Matters\n\n# Conclusion",
    },
    "Technical": {
        "instruction": "Be highly technical. Discuss architecture, pipelines, embeddings, vector databases, and scalability.",
        "format": "# Technical Overview\n\n# System Architecture\n\n# Embedding Pipeline\n\n# Retrieval Workflow\n\n# Vector Databases\n\n# Technical Challenges\n\n# Conclusion",
    },
    "Interview Prep": {
        "instruction": "Focus on interview preparation. Include FAQs, concise explanations, and revision notes.",
        "format": "# Quick Summary\n\n# Important Concepts\n\n# Most Asked Interview Questions\n\n# Common Mistakes\n\n# Revision Notes\n\n# Conclusion",
    },
    "Startup Analysis": {
        "instruction": "Think like a startup founder. Discuss monetization, competitors, and market opportunities.",
        "format": "# Market Opportunity\n\n# Competitor Analysis\n\n# Monetization Strategy\n\n# Startup Ideas\n\n# Risks\n\n# Conclusion",
    },
    "Research Paper": {
        "instruction": "Write academically and analytically.",
        "format": "# Abstract\n\n# Introduction\n\n# Technical Analysis\n\n# Limitations\n\n# Future Research\n\n# Conclusion",
    },
}


# ----------------------------------------------------------------------------
# Helpers (all synchronous/blocking — called via run_in_executor)
# ----------------------------------------------------------------------------
def domain_of(url):
    """Robust title from URL — handles http, https, and missing scheme."""
    try:
        netloc = urlparse(url).netloc
        return netloc or url
    except Exception:
        return url


def search_web(query):
    """Blocking DDG search. Runs in a worker thread, so time.sleep here is fine.
    Falls back to a Wikipedia URL if DDG returns nothing (rate-limit workaround)."""
    urls = []
    try:
        time.sleep(DDG_DELAY_SECONDS)
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=MAX_URLS))
        for r in results:
            href = r.get("href") or r.get("url")
            if href:
                urls.append(href)
    except Exception as e:
        print(f"Search error: {e}")

    if not urls:
        slug = query.strip().replace(" ", "_")
        urls = [f"https://en.wikipedia.org/wiki/{slug}"]
    return urls[:MAX_URLS]


def scrape_sync(url):
    result = firecrawl.scrape(url)
    md = getattr(result, "markdown", "") or ""
    return md[:SCRAPE_CHAR_LIMIT]


async def scrape_url(url):
    """Non-blocking scrape with a per-URL timeout."""
    loop = asyncio.get_event_loop()
    try:
        content = await asyncio.wait_for(
            loop.run_in_executor(executor, scrape_sync, url),
            timeout=SCRAPE_TIMEOUT,
        )
        return {"url": url, "content": content, "success": bool(content)}
    except Exception as e:
        print(f"Scrape error for {url}: {e}")
        return {"url": url, "content": "", "success": False}


def build_context(all_content, query):
    """RAG step (blocking embeds). Batched embedding; ephemeral collection.

    NOTE: at ~12k chars the whole corpus fits comfortably in the model's context.
    Benchmark this against simply passing all_content to the prompt — RAG only
    earns its place once the corpus grows large (e.g. an agentic multi-hop loop)."""
    if not all_content.strip():
        return "No web content could be retrieved for this query."

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
    chunks = splitter.split_text(all_content)
    if not chunks:
        return "No web content could be retrieved for this query."

    collection_name = f"research_{uuid.uuid4().hex[:8]}"
    collection = chroma_client.get_or_create_collection(name=collection_name)
    try:
        # Batch embed all chunks in ONE call (was a per-chunk loop = N round-trips).
        chunk_embeddings = embeddings.embed_documents(chunks)
        collection.add(
            ids=[str(i) for i in range(len(chunks))],
            embeddings=chunk_embeddings,
            documents=chunks,
        )
        query_embedding = embeddings.embed_query(query)
        res = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(RAG_TOP_K, len(chunks)),
        )
        docs = res["documents"][0] if res.get("documents") else []
        return "\n\n".join(docs) if docs else all_content[:SCRAPE_CHAR_LIMIT]
    except Exception as e:
        print(f"RAG error: {e}")
        return all_content[:SCRAPE_CHAR_LIMIT]
    finally:
        try:
            chroma_client.delete_collection(collection_name)
        except Exception:
            pass


def generate(prompt):
    """Blocking LLM call (offloaded to the executor by callers)."""
    response = openrouter_client.chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=GEN_TEMPERATURE,
    )
    return response.choices[0].message.content


# --- Gemini alternative (stronger generator) -------------------------------
# from google import genai
# gemini_client = genai.Client(api_key=GEMINI_API_KEY)
# def generate(prompt):
#     resp = gemini_client.models.generate_content(
#         model="gemini-2.0-flash", contents=prompt,
#     )
#     return resp.text
# ---------------------------------------------------------------------------


# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------
@app.get("/")
def home():
    return {"message": "DeepScout Backend Running"}


@app.post("/research")
async def research(data: ResearchRequest):
    start = time.time()
    query = data.query
    history = data.history
    mode = data.mode if data.mode in MODE_CONFIG else "Beginner"

    cache_key = f"{query}-{mode}"
    cached = cache_get(cache_key)
    if cached:
        print("Cache hit")
        return cached

    print(f"\nQuery: {query} | Mode: {mode}")

    loop = asyncio.get_event_loop()

    # 1) SEARCH (non-blocking)
    urls = await loop.run_in_executor(executor, search_web, query)
    print(f"URLs found: {len(urls)}")

    # 2) SCRAPE (parallel, each with a timeout)
    scrape_results = (
        await asyncio.gather(*[scrape_url(u) for u in urls]) if urls else []
    )

    all_content = ""
    sources = []
    for item in scrape_results:
        if item["success"] and item["content"]:
            all_content += f"\n\nSOURCE: {item['url']}\n{item['content']}"
            sources.append({"title": domain_of(item["url"]), "url": item["url"]})

    # 3) RAG (non-blocking — embeds run in the executor)
    retrieved_context = await loop.run_in_executor(
        executor, build_context, all_content, query
    )

    # 4) PROMPT
    cfg = MODE_CONFIG[mode]
    previous_context = ""
    for item in history[-3:]:
        previous_context += (
            f"\nUser: {item.get('query', '')}"
            f"\nAssistant: {item.get('report', '')[:300]}\n"
        )

    prompt = f"""
You are DeepScout AI.

CURRENT USER QUERY:
{query}

CURRENT MODE:
{mode}

MODE INSTRUCTIONS:
{cfg['instruction']}

PREVIOUS CONTEXT:
{previous_context}

RETRIEVED CONTEXT:
{retrieved_context}

STRICTLY FOLLOW THIS STRUCTURE:
{cfg['format']}

IMPORTANT:
- Make each mode genuinely different
- Use markdown formatting
- Keep response concise and useful
- Avoid filler text
- Base claims on the RETRIEVED CONTEXT; do not invent facts

IF the query includes comparisons, "vs", or alternatives:
- generate markdown comparison tables and compare side-by-side
"""

    # 5) GENERATE (non-blocking, with timeout)
    ok = True
    try:
        report = await asyncio.wait_for(
            loop.run_in_executor(executor, generate, prompt),
            timeout=LLM_TIMEOUT + 5,
        )
        print("Generation OK")
    except Exception as e:
        print(f"Generation error: {e}")
        report = (
            "AI generation failed. Check OPENROUTER_API_KEY / model availability."
        )
        ok = False

    final_response = {"report": report, "sources": sources}
    if ok:
        cache_set(cache_key, final_response)

    print(f"Total time: {round(time.time() - start, 2)}s")
    return final_response


@app.post("/follow-up")
async def follow_up(data: FollowUpRequest):
    question = data.question
    report = data.report
    mode = data.mode if data.mode in MODE_CONFIG else "Beginner"

    prompt = f"""
You are DeepScout AI.

REPORT:
{report[:2500]}

FOLLOW-UP QUESTION:
{question}

CURRENT MODE:
{mode}

IMPORTANT:
- Answer specifically using the report above
- Be concise
- Use markdown
- Do NOT regenerate the full report

FORMAT:

# Answer

# Key Points
"""

    loop = asyncio.get_event_loop()
    try:
        answer = await asyncio.wait_for(
            loop.run_in_executor(executor, generate, prompt),
            timeout=LLM_TIMEOUT + 5,
        )
        print("Follow-up OK")
    except Exception as e:
        print(f"Follow-up error: {e}")
        answer = "Failed to generate follow-up response."

    return {"answer": answer}
