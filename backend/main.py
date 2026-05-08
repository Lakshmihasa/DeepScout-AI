from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from firecrawl import FirecrawlApp
import requests
import os

# Load env
load_dotenv()

# API keys
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Firecrawl setup
firecrawl = FirecrawlApp(api_key=FIRECRAWL_API_KEY)

# FastAPI app
app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request model
class ResearchRequest(BaseModel):
    query: str

@app.get("/")
def home():
    return {
        "message": "DeepScout Backend Running"
    }

@app.post("/research")
def research(data: ResearchRequest):

    query = data.query

    urls = [
        "https://cursor.com",
        "https://windsurf.com",
        "https://github.com/features/copilot"
    ]

    all_content = ""

    # Scrape websites
    for url in urls:
        try:
            result = firecrawl.scrape(url)

            content = result.markdown

            all_content += f"\n\nSOURCE: {url}\n"
            all_content += content[:1500]

        except Exception as e:
            print(f"Scraping error: {e}")

    prompt = f"""
You are DeepScout AI.

Generate a professional AI research report.

Research Topic:
{query}

Analyze this scraped content:

{all_content}

Format:
# Overview
# Key Insights
# Trends
# Conclusion
"""

    try:

        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "minimax/minimax-m2.5:free",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }
        )

        result = response.json()

        report = result["choices"][0]["message"]["content"]

        return {
            "report": report
        }

    except Exception as e:
        return {
            "report": f"AI Error: {str(e)}"
        }