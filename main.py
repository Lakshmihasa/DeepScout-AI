import os
from dotenv import load_dotenv
from firecrawl import FirecrawlApp
from openai import OpenAI

# Load environment variables
load_dotenv()

# API Keys
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Initialize Firecrawl
firecrawl = FirecrawlApp(api_key=FIRECRAWL_API_KEY)

# Initialize OpenRouter client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# User topic
topic = input("Enter research topic: ")

# URLs to scrape
urls = [
    "https://cursor.com",
    "https://windsurf.com",
    "https://github.com/features/copilot"
]

all_content = ""

print("\n🔎 DeepScout is researching the web...\n")

# Scrape websites
for url in urls:
    try:
        result = firecrawl.scrape(url)

        content = result.markdown

        all_content += f"\n\nSOURCE: {url}\n"
        all_content += content[:1500]

        print(f"✅ Scraped: {url}")

    except Exception as e:
        print(f"❌ Error scraping {url}: {e}")

print("\n🧠 Generating AI research report...\n")

# Prompt
prompt = f"""
You are DeepScout, an elite AI research analyst.

Research Topic:
{topic}

Analyze the following scraped website content.

Generate a structured report with:

# Overview
# Key Features
# Strengths
# Weaknesses
# Interesting Insights
# Final Conclusion

Be concise, insightful, and analytical.

CONTENT:
{all_content}
"""

try:
    response = client.chat.completions.create(
        model="minimax/minimax-m2.5:free",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    report = response.choices[0].message.content

    # Create research folder
    os.makedirs("research", exist_ok=True)

    # Create filename
    filename = topic.lower().replace(" ", "-") + ".md"

    filepath = f"research/{filename}"

    # Save report
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    print("\n✅ Research completed successfully!")
    print(f"📄 Report saved to: {filepath}")

except Exception as e:
    print(f"\n❌ AI Model Error: {e}")