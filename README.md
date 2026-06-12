# 🔍 DeepScout AI

> **Autonomous research assistant** that searches the web, scrapes live sources, and generates structured reports — so you don't have to open 10 tabs.

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Frontend-Next.js-000000?style=flat-square&logo=nextdotjs)](https://nextjs.org/)
[![Gemini AI](https://img.shields.io/badge/AI-Gemini-4285F4?style=flat-square&logo=google)](https://deepmind.google/technologies/gemini/)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

---

## What is DeepScout?

Most AI tools answer questions from training data. DeepScout goes further — it **actively researches the internet in real time**, extracts content from relevant sources, and synthesizes everything into a structured report tailored to your context.

Instead of manually Googling → opening tabs → reading articles → taking notes → summarizing findings, DeepScout does all of that automatically in seconds.

```
User query
    ↓
DuckDuckGo Search  →  Find relevant URLs
    ↓
Firecrawl          →  Scrape & extract content
    ↓
Gemini AI          →  Analyze & synthesize
    ↓
Structured Report  →  Tailored to your mode
    ↓
Follow-up Q&A      →  Conversational insights
```

---

## Research Modes

DeepScout adapts its output based on **who is asking** and **why** — not just what the topic is.

| Mode | Best For | Output Shape |
|------|----------|--------------|
| 🟢 **Beginner** | Students, newcomers | Simple explanation → real-world analogy → examples |
| 🔵 **Technical** | Developers, engineers | Architecture → implementation details → code concepts |
| 🟡 **Interview Prep** | Job seekers | Key concepts → common questions → model answers → mistakes to avoid |
| 🟠 **Startup Analysis** | Founders, PMs | Market size → competitors → monetization → risks |
| 🔴 **Research Paper** | Academics, researchers | Background → methodology → findings → citations |

**Example:** Topic = "What is RAG?"

- Beginner Mode → *"Imagine an open-book exam where the AI looks up answers before responding..."*
- Technical Mode → *"Embeddings, vector databases, retrieval pipeline, chunking strategies..."*
- Interview Prep → *"Top 10 interview questions, model answers, common mistakes..."*
- Startup Analysis → *"$2.3B market, key players (Perplexity, You.com), revenue models..."*

---

## Tech Stack

### Backend
- **FastAPI** — async Python API server
- **DuckDuckGo Search** — live web search (no API key required)
- **Firecrawl** — intelligent web scraping and content extraction
- **Gemini AI** — report generation and follow-up Q&A

### Frontend
- **Next.js 14** — React framework with App Router
- **Tailwind CSS** — utility-first styling
- **TypeScript** — type-safe frontend

### Infrastructure
- **Render** — backend and frontend deployment
- **PostgreSQL** — conversation and report persistence

---

## Getting Started

### Prerequisites

```bash
Python 3.10+
Node.js 18+
```

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/deepscout-ai.git
cd deepscout-ai
```

### 2. Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in `/backend`:

```env
GEMINI_API_KEY=your_gemini_api_key
FIRECRAWL_API_KEY=your_firecrawl_api_key
DATABASE_URL=your_postgresql_url
```

Start the backend:

```bash
uvicorn main:app --reload --port 8000
```

### 3. Frontend setup

```bash
cd frontend
npm install
```

Create a `.env.local` file in `/frontend`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Start the frontend:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## Project Structure

```
deepscout-ai/
├── backend/
│   ├── main.py               # FastAPI app entry point
│   ├── routers/
│   │   ├── research.py       # Research generation endpoints
│   │   └── followup.py       # Follow-up Q&A endpoints
│   ├── services/
│   │   ├── search.py         # DuckDuckGo search logic
│   │   ├── scraper.py        # Firecrawl scraping logic
│   │   └── generator.py      # Gemini AI report generation
│   ├── models/
│   │   └── schemas.py        # Pydantic request/response models
│   └── requirements.txt
│
├── frontend/
│   ├── app/
│   │   ├── page.tsx          # Home / search page
│   │   ├── report/[id]/      # Report display page
│   │   └── layout.tsx
│   ├── components/
│   │   ├── SearchBar.tsx
│   │   ├── ModeSelector.tsx
│   │   ├── ReportView.tsx
│   │   └── FollowUpChat.tsx
│   └── package.json
│
└── README.md
```

---

## API Reference

### `POST /research`

Generate a research report.

**Request body:**
```json
{
  "query": "What is RAG?",
  "mode": "technical",
  "max_sources": 5
}
```

**Response:**
```json
{
  "report_id": "rpt_abc123",
  "title": "Retrieval-Augmented Generation (RAG)",
  "sections": [...],
  "sources": [...],
  "generated_at": "2025-06-12T10:30:00Z"
}
```

### `POST /followup`

Ask a follow-up question on an existing report.

**Request body:**
```json
{
  "report_id": "rpt_abc123",
  "question": "What vector databases work best for RAG?"
}
```

---

## Roadmap

- [x] Multi-mode report generation
- [x] Follow-up Q&A on reports
- [x] FastAPI + Next.js full-stack deployment
- [ ] Streaming report generation (real-time section-by-section output)
- [ ] Source citations with per-claim grounding
- [ ] Agentic multi-step research loop (ReAct)
- [ ] Debate Mode — parallel agents arguing both sides
- [ ] Knowledge graph linking related reports
- [ ] PDF / YouTube URL as research input
- [ ] Evaluation dashboard (hallucination rate, coverage score)

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Google Gemini API key |
| `FIRECRAWL_API_KEY` | Yes | Firecrawl scraping API key |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `NEXT_PUBLIC_API_URL` | Yes | Backend API base URL |

---

## Contributing

This project is currently in active development. Contributions, issues, and feature requests are welcome.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -m 'Add your feature'`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request

---

## Author

**Lakshmi Hasa** — Incoming MS AI @ SJSU | Full-Stack AI Engineer

[![GitHub](https://img.shields.io/badge/GitHub-@yourusername-181717?style=flat-square&logo=github)](https://github.com/yourusername)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0A66C2?style=flat-square&logo=linkedin)](https://linkedin.com/in/yourprofile)

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

> ⚠️ **Note:** This README is a working draft. API keys, deployment URLs, and GitHub links will be updated as the project progresses.