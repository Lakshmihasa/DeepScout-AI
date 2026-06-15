from openai import OpenAI
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from firecrawl import FirecrawlApp
from ddgs import DDGS
from google import genai
from google.genai import types
import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
import time
import uuid
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
import chromadb


# LOAD ENV

load_dotenv()
import os

print("CWD:", os.getcwd())
print("ENV FILE CHECK:", os.path.exists(".env"))
print("OPENROUTER:", os.getenv("OPENROUTER_API_KEY"))

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# API KEYS

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

print("Gemini key exists:", bool(GEMINI_API_KEY))
print("OpenRouter key exists:", bool(OPENROUTER_API_KEY))

print("Gemini key exists:", bool(GEMINI_API_KEY))

# GEMINI CONFIG (embeddings only)

client = genai.Client(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-2.0-flash"

embeddings = GoogleGenerativeAIEmbeddings(
    model="models/text-embedding-004",
    google_api_key=GEMINI_API_KEY
)

# ChromaDB — no global collection, created per-request

chroma_client = chromadb.PersistentClient(path="./chroma_db")

# FIRECRAWL

firecrawl = FirecrawlApp(api_key=FIRECRAWL_API_KEY)

# FASTAPI

app = FastAPI()

# CORS

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CACHE

CACHE = {}
CACHE_EXPIRY = 60 * 30

# REQUEST MODELS

class ResearchRequest(BaseModel):
    query: str
    history: list = []
    mode: str = "Beginner"

class FollowUpRequest(BaseModel):
    question: str
    report: str
    mode: str = "Beginner"

# HOME

@app.get("/")
def home():
    return {"message": "DeepScout Backend Running"}

# ASYNC SCRAPER

executor = ThreadPoolExecutor(max_workers=5)

async def scrape_url(url):

    loop = asyncio.get_event_loop()

    try:

        result = await loop.run_in_executor(
            executor,
            lambda: firecrawl.scrape(url)
        )

        content = result.markdown[:3000] if result.markdown else ""

        return {
            "url": url,
            "content": content,
            "success": True
        }

    except Exception as e:

        print(f"❌ Scraping Error for {url}: {e}")

        return {
            "url": url,
            "content": "",
            "success": False
        }

# RESEARCH ENDPOINT

@app.post("/research")
async def research(data: ResearchRequest):

    start_time = time.time()

    query = data.query
    history = data.history
    mode = data.mode

    cache_key = f"{query}-{mode}"

    # CACHE CHECK

    if cache_key in CACHE:
        cached_item = CACHE[cache_key]
        if time.time() - cached_item["timestamp"] < CACHE_EXPIRY:
            print("⚡ Returning Cached Response")
            return cached_item["data"]

    print(f"\n🔎 Query: {query}")
    print(f"🧠 Mode: {mode}")

    # SEARCH WEB

    urls = []

    try:
        with DDGS() as ddgs:
            time.sleep(1)  # avoid rate limit
            results = list(ddgs.text(query, max_results=4))
            for result in results:
                if "href" in result:
                    urls.append(result["href"])
    except Exception as e:
        print(f"❌ Search Error: {e}")

    print(f"🌐 URLs Found: {len(urls)}")

    # SCRAPE IN PARALLEL

    if urls:
        scrape_results = await asyncio.gather(
            *[scrape_url(url) for url in urls]
        )
    else:
        scrape_results = []

    all_content = ""
    sources = []

    for item in scrape_results:

        if item["success"] and item["content"]:

            all_content += f"\n\nSOURCE: {item['url']}\n"
            all_content += item["content"]

            sources.append({
                "title": item["url"].replace("https://", "").split("/")[0],
                "url": item["url"]
            })

    # =====================
    # RAG PIPELINE
    # =====================

    retrieved_context = ""

    if all_content.strip():

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=100
        )

        chunks = text_splitter.split_text(all_content)

        print(f"📚 Chunks Created: {len(chunks)}")

        collection_name = f"research_{uuid.uuid4().hex[:8]}"
        collection = chroma_client.get_or_create_collection(name=collection_name)

        try:

            for idx, chunk in enumerate(chunks):

                embedding = embeddings.embed_query(chunk)

                collection.add(
                    ids=[str(idx)],
                    embeddings=[embedding],
                    documents=[chunk]
                )

            query_embedding = embeddings.embed_query(query)

            rag_results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(4, len(chunks))
            )

            retrieved_context = "\n\n".join(rag_results["documents"][0])

            print(f"🎯 Retrieved Chunks: {len(rag_results['documents'][0])}")

        except Exception as e:

            print(f"❌ RAG Error: {e}")
            retrieved_context = all_content[:3000]

        finally:

            try:
                chroma_client.delete_collection(collection_name)
            except Exception:
                pass

    else:

        print("⚠️ No content scraped — skipping RAG")
        retrieved_context = "No web content could be retrieved for this query."

    # PREVIOUS CONTEXT

    previous_context = ""

    for item in history[-3:]:
        previous_context += f"""
User: {item.get('query', '')}
Assistant: {item.get('report', '')[:300]}
"""

    # MODE CONFIGS

    format_template = ""
    mode_instruction = ""

    if mode == "Beginner":

        mode_instruction = """
Explain in simple language.
Use examples and analogies.
Avoid heavy jargon.
"""

        format_template = """
# Overview

# Simple Explanation

# Easy Example

# Why It Matters

# Conclusion
"""

    elif mode == "Technical":

        mode_instruction = """
Be highly technical.
Discuss architecture, pipelines, embeddings, vector databases, and scalability.
"""

        format_template = """
# Technical Overview

# System Architecture

# Embedding Pipeline

# Retrieval Workflow

# Vector Databases

# Technical Challenges

# Conclusion
"""

    elif mode == "Interview Prep":

        mode_instruction = """
Focus on interview preparation.
Include FAQs, concise explanations, and revision notes.
"""

        format_template = """
# Quick Summary

# Important Concepts

# Most Asked Interview Questions

# Common Mistakes

# Revision Notes

# Conclusion
"""

    elif mode == "Startup Analysis":

        mode_instruction = """
Think like a startup founder.
Discuss monetization, competitors, and market opportunities.
"""

        format_template = """
# Market Opportunity

# Competitor Analysis

# Monetization Strategy

# Startup Ideas

# Risks

# Conclusion
"""

    elif mode == "Research Paper":

        mode_instruction = """
Write academically and analytically.
"""

        format_template = """
# Abstract

# Introduction

# Technical Analysis

# Limitations

# Future Research

# Conclusion
"""

    # AI PROMPT

    prompt = f"""
You are DeepScout AI.

CURRENT USER QUERY:
{query}

CURRENT MODE:
{mode}

MODE INSTRUCTIONS:
{mode_instruction}

PREVIOUS CONTEXT:
{previous_context}

RETRIEVED CONTEXT:
{retrieved_context}

STRICTLY FOLLOW THIS STRUCTURE:
{format_template}

IMPORTANT:
- Make each mode genuinely different
- Use markdown formatting
- Keep response concise and useful
- Avoid filler text

IF query includes:
- comparisons
- vs
- alternatives

THEN:
- generate markdown comparison tables
- compare side-by-side
"""

    # OPENROUTER GENERATION

    report = None

    try:

        response = openrouter_client.chat.completions.create(
            model="openai/gpt-oss-20b:free",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
        )

        report = response.choices[0].message.content

        print("✅ OpenRouter Success")

    except Exception as e:

        print(f"❌ OpenRouter Error: {e}")
        report = f"AI generation failed: {str(e)}\n\nCheck your OPENROUTER_API_KEY and model availability."

    final_response = {
        "report": report,
        "sources": sources
    }

    # Only cache successful responses
    if "AI generation failed" not in report:
        CACHE[cache_key] = {
            "timestamp": time.time(),
            "data": final_response
        }

    print(f"⚡ Total Time: {round(time.time() - start_time, 2)}s")

    return final_response


# FOLLOW-UP CHAT

@app.post("/follow-up")
async def follow_up(data: FollowUpRequest):

    question = data.question
    report = data.report
    mode = data.mode

    prompt = f"""
You are DeepScout AI.

REPORT:
{report[:2500]}

FOLLOW-UP QUESTION:
{question}

CURRENT MODE:
{mode}

IMPORTANT:
- Answer specifically
- Be concise
- Use markdown
- Do NOT regenerate the full report

FORMAT:

# Answer

# Key Points
"""

    answer = None

    try:

        response = openrouter_client.chat.completions.create(
            model="openai/gpt-oss-20b:free",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
        )

        answer = response.choices[0].message.content

        print("✅ Follow-up Success")

    except Exception as e:

        print(f"❌ Follow-up Error: {e}")
        answer = f"Failed to generate follow-up response: {str(e)}"

    return {"answer": answer}