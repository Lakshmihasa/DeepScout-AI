"use client";

import { useEffect, useRef, useState } from "react";
import jsPDF from "jspdf";
import html2canvas from "html2canvas-pro";
import ReactMarkdown from "react-markdown";

export default function Home() {

  const [query, setQuery] = useState("");
  const [response, setResponse] = useState("");
  const [sources, setSources] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  // AI MODE

  const [mode, setMode] = useState("Beginner");

  // FOLLOW-UP CHAT

  const [followUp, setFollowUp] = useState("");
  const [followUpResponse, setFollowUpResponse] = useState("");
  const [followUpLoading, setFollowUpLoading] = useState(false);

  // HISTORY

  const [history, setHistory] = useState<any[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const reportRef = useRef<HTMLDivElement>(null);

  // LOAD HISTORY

  useEffect(() => {

    const savedHistory = localStorage.getItem("deepscout-history");

    if (savedHistory) {

      setHistory(JSON.parse(savedHistory));
    }

  }, []);

  // SAVE HISTORY

  useEffect(() => {

    localStorage.setItem(
      "deepscout-history",
      JSON.stringify(history)
    );

  }, [history]);

  // STREAM EFFECT

  async function streamText(text: string) {

    let currentText = "";

    for (let i = 0; i < text.length; i++) {

      currentText += text[i];

      setResponse(currentText);

      await new Promise((resolve) =>
        setTimeout(resolve, 5)
      );
    }
  }

  // GENERATE REPORT

  async function generateReport() {

    try {

      setLoading(true);

      setResponse("");

      setFollowUpResponse("");

      const res = await fetch(
        "http://127.0.0.1:8000/research",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            query,
            history,
            mode
          }),
        }
      );

      const data = await res.json();

      const report = data.report || "No report returned";

      const sourceData = data.sources || [];

      setSources(sourceData);

      await streamText(report);

      const newHistoryItem = {
        query,
        report,
        sources: sourceData
      };

      setHistory((prev) => [
        newHistoryItem,
        ...prev
      ]);

    } catch (error) {

      console.error(error);

      setResponse("Failed to generate report.");

    } finally {

      setLoading(false);
    }
  }

  // FOLLOW-UP CHAT

  async function askFollowUp() {

    if (!followUp.trim()) return;

    try {

      setFollowUpLoading(true);

      const res = await fetch(
        "http://127.0.0.1:8000/follow-up",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            question: followUp,
            report: response,
            mode
          }),
        }
      );

      const data = await res.json();

      setFollowUpResponse(data.answer);

    } catch (error) {

      console.error(error);

      setFollowUpResponse(
        "Failed to generate follow-up response."
      );

    } finally {

      setFollowUpLoading(false);
    }
  }

  // TXT DOWNLOAD

  function downloadTXT() {

    const blob = new Blob([response], {
      type: "text/plain"
    });

    const url = window.URL.createObjectURL(blob);

    const a = document.createElement("a");

    a.href = url;

    a.download = "deepscout-report.txt";

    a.click();
  }

  // PDF DOWNLOAD

  async function downloadPDF() {

    if (!reportRef.current) return;

    try {

      const canvas = await html2canvas(
        reportRef.current,
        {
          scale: 2,
          useCORS: true,
          logging: false,
          backgroundColor: "#111827",
        }
      );

      const imgData = canvas.toDataURL("image/png");

      const pdf = new jsPDF({
        orientation: "portrait",
        unit: "mm",
        format: "a4"
      });

      const pdfWidth =
        pdf.internal.pageSize.getWidth();

      const imgProps =
        pdf.getImageProperties(imgData);

      const pdfHeight =
        (imgProps.height * pdfWidth) /
        imgProps.width;

      pdf.addImage(
        imgData,
        "PNG",
        0,
        0,
        pdfWidth,
        pdfHeight
      );

      pdf.save("DeepScout-Report.pdf");

    } catch (error) {

      console.error("PDF Export Error:", error);

    }
  }

  // CLEAR HISTORY

  function clearHistory() {

    localStorage.removeItem(
      "deepscout-history"
    );

    setHistory([]);
  }

  return (

    <main className="min-h-screen bg-[#0f172a] text-white flex overflow-hidden">

      {/* SIDEBAR */}

      <aside className={`
        fixed md:relative z-50 md:z-auto
        w-[300px] h-full
        border-r border-white/10
        bg-black/30 backdrop-blur-xl
        p-6 overflow-y-auto
        transition-transform duration-300
        ${sidebarOpen
          ? "translate-x-0"
          : "-translate-x-full"}
        md:translate-x-0
      `}>

        <div className="mb-10">

          <h1 className="text-3xl font-black text-cyan-300">
            DeepScout
          </h1>

          <p className="text-zinc-400 mt-2">
            AI Research History
          </p>

        </div>

        <button
          onClick={clearHistory}
          className="mb-6 bg-red-500/20 border border-red-400/30 text-red-300 px-4 py-2 rounded-xl text-sm hover:bg-red-500/30 transition"
        >
          Clear History
        </button>

        <div className="space-y-4">

          {history.length === 0 && (

            <div className="text-zinc-500 text-sm">
              No reports generated yet.
            </div>

          )}

          {history.map((item, index) => (

            <button
              key={index}
              onClick={() => {

                setResponse(item.report);

                setSources(item.sources);

                setQuery(item.query);

              }}
              className="w-full text-left bg-white/5 border border-white/10 hover:border-cyan-400/40 rounded-2xl p-4 transition"
            >

              <div className="text-cyan-300 font-semibold mb-2">
                Research #{history.length - index}
              </div>

              <div className="text-zinc-300 text-sm line-clamp-2">
                {item.query}
              </div>

            </button>

          ))}

        </div>

      </aside>

      {/* MAIN */}

      <div className="flex-1 overflow-y-auto px-4 md:px-6 py-8 md:py-12 w-full">

        <div className="relative max-w-6xl mx-auto">

          {/* HERO */}

          <div className="text-center mb-12 md:mb-16">

            <div className="inline-block px-5 py-2 rounded-full border border-cyan-400/20 bg-white/5 backdrop-blur mb-6 text-sm md:text-base">
              ✨ Autonomous AI Research Platform
            </div>

            <h1 className="text-5xl md:text-8xl font-black text-cyan-300">
              DeepScout AI
            </h1>

            <p className="text-zinc-300 text-base md:text-xl max-w-3xl mx-auto mt-6 leading-8 md:leading-9">
              Research the web, analyze sources,
              generate structured reports,
              and uncover insights powered by AI agents.
            </p>

          </div>

          {/* SEARCH */}

          <div className="max-w-4xl mx-auto">

            <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-3xl p-3 shadow-2xl">

              <div className="flex flex-col md:flex-row gap-3">

                {/* MODE */}

                <select
                  value={mode}
                  onChange={(e) =>
                    setMode(e.target.value)
                  }
                  className="bg-white/10 border border-white/10 rounded-2xl px-4 py-3 text-white outline-none min-w-[200px]"
                >

                  <option className="text-black">
                    Beginner
                  </option>

                  <option className="text-black">
                    Technical
                  </option>

                  <option className="text-black">
                    Interview Prep
                  </option>

                  <option className="text-black">
                    Startup Analysis
                  </option>

                  <option className="text-black">
                    Research Paper
                  </option>

                </select>

                {/* INPUT */}

                <input
                  type="text"
                  placeholder="Ask DeepScout anything..."
                  value={query}
                  onChange={(e) =>
                    setQuery(e.target.value)
                  }
                  className="flex-1 bg-transparent outline-none px-4 py-3 text-lg placeholder:text-zinc-500"
                />

                {/* BUTTON */}

                <button
                  onClick={generateReport}
                  disabled={loading}
                  className="bg-cyan-400 text-black px-8 py-4 rounded-2xl font-bold hover:scale-105 transition disabled:opacity-50"
                >

                  {loading ? (

                    <div className="flex items-center justify-center gap-3">

                      <div className="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin"></div>

                      <span>
                        Researching
                      </span>

                    </div>

                  ) : (

                    "Generate Report"

                  )}

                </button>

              </div>

            </div>

          </div>

          {/* SOURCES */}

          {sources.length > 0 && (

            <div className="mt-16">

              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">

                <h2 className="text-3xl md:text-4xl font-bold">
                  Sources
                </h2>

                <div className="text-zinc-400">
                  {sources.length} sources analyzed
                </div>

              </div>

              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">

                {sources.map((source, index) => (

                  <a
                    key={index}
                    href={source.url}
                    target="_blank"
                    className="group bg-white/5 backdrop-blur-xl border border-white/10 hover:border-cyan-400/50 rounded-3xl p-6 transition duration-300 hover:-translate-y-1"
                  >

                    <div className="text-4xl mb-4">
                      🌐
                    </div>

                    <h3 className="font-bold text-xl mb-3 break-all group-hover:text-cyan-300">
                      {source.title}
                    </h3>

                    <p className="text-zinc-400 text-sm break-all">
                      {source.url}
                    </p>

                  </a>

                ))}

              </div>

            </div>
          )}

          {/* REPORT */}

          {response && (

            <div
              ref={reportRef}
              className="mt-16 bg-white/5 backdrop-blur-xl border border-white/10 rounded-[2rem] p-6 md:p-10 shadow-2xl"
            >

              <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-6 mb-10">

                <div>

                  <h2 className="text-3xl md:text-4xl font-bold">
                    Research Report
                  </h2>

                  <p className="text-zinc-400 mt-2">
                    Generated by DeepScout AI • {mode} Mode
                  </p>

                </div>

                <div className="flex flex-col sm:flex-row gap-3">

                  <button
                    onClick={downloadTXT}
                    className="bg-cyan-400 text-black px-5 py-3 rounded-xl font-semibold hover:scale-105 transition"
                  >
                    Download TXT
                  </button>

                  <button
                    onClick={downloadPDF}
                    className="bg-fuchsia-500 text-white px-5 py-3 rounded-xl font-semibold hover:scale-105 transition"
                  >
                    Export PDF
                  </button>

                </div>

              </div>

              {/* MARKDOWN */}

              <div className="max-w-none text-zinc-200 leading-9">

                <ReactMarkdown
                  components={{

                    h1: ({ children }) => (
                      <div className="mt-14 mb-6">

                        <div className="inline-block px-5 py-2 rounded-2xl bg-cyan-500/20 border border-cyan-400/20 mb-4">

                          <h1 className="text-3xl md:text-4xl font-black text-cyan-300">
                            {children}
                          </h1>

                        </div>

                      </div>
                    ),

                    h2: ({ children }) => (
                      <h2 className="text-2xl md:text-3xl font-bold text-fuchsia-300 mt-12 mb-5 border-l-4 border-fuchsia-400 pl-4">
                        {children}
                      </h2>
                    ),

                    h3: ({ children }) => (
                      <h3 className="text-xl md:text-2xl font-semibold text-cyan-200 mt-8 mb-4">
                        {children}
                      </h3>
                    ),

                    p: ({ children }) => (
                      <p className="text-zinc-300 text-base md:text-lg leading-8 md:leading-9 mb-6">
                        {children}
                      </p>
                    ),

                    li: ({ children }) => (
                      <li className="mb-3 text-zinc-300 text-base md:text-lg">
                        ✦ {children}
                      </li>
                    ),

                    strong: ({ children }) => (
                      <strong className="text-white font-bold">
                        {children}
                      </strong>
                    ),

                  }}
                >
                  {response}
                </ReactMarkdown>

              </div>

              {/* FOLLOW-UP CHAT */}

              <div className="mt-14 border-t border-white/10 pt-10">

                <h3 className="text-2xl font-bold mb-6 text-cyan-300">
                  Ask Follow-Up Questions
                </h3>

                <div className="flex flex-col md:flex-row gap-4">

                  <input
                    type="text"
                    placeholder="Ask deeper questions about this report..."
                    value={followUp}
                    onChange={(e) =>
                      setFollowUp(e.target.value)
                    }
                    className="flex-1 bg-white/5 border border-white/10 rounded-2xl px-5 py-4 outline-none text-white"
                  />

                  <button
                    onClick={askFollowUp}
                    disabled={followUpLoading}
                    className="bg-fuchsia-500 px-6 py-4 rounded-2xl font-bold hover:scale-105 transition"
                  >

                    {followUpLoading
                      ? "Thinking..."
                      : "Ask AI"}

                  </button>

                </div>

                {/* FOLLOW-UP RESPONSE */}

                {followUpResponse && (

                  <div className="mt-8 bg-black/20 border border-white/10 rounded-3xl p-6">

                    <ReactMarkdown>

                      {followUpResponse}

                    </ReactMarkdown>

                  </div>

                )}

              </div>

            </div>
          )}

        </div>

      </div>

    </main>
  );
}