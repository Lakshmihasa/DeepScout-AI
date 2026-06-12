from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from firecrawl import FirecrawlApp
from duckduckgo_search import DDGS
import google.generativeai as genai
import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
import time

# LOAD ENV

load_dotenv()

# API KEYS

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# GEMINI CONFIG

genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel(
    "gemini-1.5-flash-latest"
)

# FIRECRAWL

firecrawl = FirecrawlApp(
    api_key=FIRECRAWL_API_KEY
)

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
    return {
        "message": "DeepScout Backend Running"
    }

# ASYNC SCRAPER

executor = ThreadPoolExecutor(max_workers=5)

async def scrape_url(url):

    loop = asyncio.get_event_loop()

    try:

        result = await loop.run_in_executor(
            executor,
            lambda: firecrawl.scrape(url)
        )

        content = result.markdown[:200]

        return {
            "url": url,
            "content": content,
            "success": True
        }

    except Exception as e:

        print(f"❌ Scraping Error: {e}")

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

            results = ddgs.text(
                query,
                max_results=1
            )

            for result in results:

                if "href" in result:

                    urls.append(result["href"])

    except Exception as e:

        print(f"❌ Search Error: {e}")

    print("\n🌐 URLs:")
    print(urls)

    # SCRAPE IN PARALLEL

    scrape_results = await asyncio.gather(
        *[scrape_url(url) for url in urls]
    )

    all_content = ""
    sources = []

    for item in scrape_results:

        if item["success"]:

            all_content += f"\n\nSOURCE: {item['url']}\n"
            all_content += item["content"]

            sources.append({
                "title": item["url"].replace(
                    "https://",
                    ""
                ).split("/")[0],
                "url": item["url"]
            })

    # PREVIOUS CONTEXT

    previous_context = ""

    for item in history[-2:]:

        previous_context += f"""
User: {item.get('query', '')}

Assistant:
{item.get('report', '')[:300]}
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

WEB CONTENT:
{all_content}

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

    # GEMINI GENERATION

    report = None

    try:

        response = model.generate_content(
            prompt
        )

        report = response.text

        print("✅ Gemini Success")

    except Exception as e:

        print(f"❌ Gemini Error: {e}")

    if report is None:

        report = "AI generation failed."

    final_response = {
        "report": report,
        "sources": sources
    }

    # SAVE CACHE

    CACHE[cache_key] = {
        "timestamp": time.time(),
        "data": final_response
    }

    print(
        f"⚡ Total Time: {round(time.time() - start_time, 2)}s"
    )

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

        response = model.generate_content(
            prompt
        )

        answer = response.text

        print("✅ Follow-up Success")

    except Exception as e:

        print(f"❌ Follow-up Error: {e}")

    if answer is None:

        answer = "Failed to generate follow-up response."

    return {
        "answer": answer
    }