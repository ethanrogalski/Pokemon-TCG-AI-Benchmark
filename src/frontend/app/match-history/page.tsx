"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

interface Match {
  id: string;
  aiAgent1: string;
  aiAgent2: string;
  winner: string;
  date: string;
  format: string;
  duration: string;
  turns: number;
  finalScore: string;
}

export default function MatchHistory() {
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "claude" | "gpt" | "gemini">(
    "all",
  );

  useEffect(() => {
    fetchMatchHistory();
  }, []);

  const fetchMatchHistory = async () => {
    try {
      setLoading(true);
      setError(null);

      // Replace with your actual API endpoint
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8080"}/api/matches`,
        {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
          },
          credentials: "include",
        },
      );

      if (!response.ok) {
        throw new Error(`Failed to fetch matches: ${response.status}`);
      }

      const data = await response.json();
      setMatches(data.matches || []);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load match history",
      );
      // Mock data for demonstration
      setMatches([
        {
          id: "1",
          aiAgent1: "Claude 3.5 Haiku",
          aiAgent2: "GPT-4",
          winner: "Claude 3.5 Haiku",
          date: "2026-05-05",
          format: "Standard",
          duration: "15:32",
          turns: 24,
          finalScore: "6-2",
        },
        {
          id: "2",
          aiAgent1: "Gemini Pro",
          aiAgent2: "Claude 3.5 Haiku",
          winner: "Claude 3.5 Haiku",
          date: "2026-05-04",
          format: "Expanded",
          duration: "22:15",
          turns: 31,
          finalScore: "6-3",
        },
        {
          id: "3",
          aiAgent1: "GPT-4",
          aiAgent2: "Simple Bot",
          winner: "GPT-4",
          date: "2026-05-03",
          format: "Standard",
          duration: "18:45",
          turns: 28,
          finalScore: "6-1",
        },
        {
          id: "4",
          aiAgent1: "Claude 3.5 Haiku",
          aiAgent2: "Gemini Pro",
          winner: "Gemini Pro",
          date: "2026-05-02",
          format: "Unlimited",
          duration: "19:12",
          turns: 26,
          finalScore: "6-4",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const filteredMatches = matches.filter((m) => {
    if (filter === "all") return true;
    if (filter === "claude") return m.winner.includes("Claude");
    if (filter === "gpt") return m.winner.includes("GPT");
    if (filter === "gemini") return m.winner.includes("Gemini");
    return true;
  });

  const stats = {
    total: matches.length,
    claudeWins: matches.filter((m) => m.winner.includes("Claude")).length,
    gptWins: matches.filter((m) => m.winner.includes("GPT")).length,
    geminiWins: matches.filter((m) => m.winner.includes("Gemini")).length,
    avgDuration:
      matches.length > 0
        ? (
            matches.reduce((sum, m) => {
              const [min, sec] = m.duration.split(":").map(Number);
              return sum + min * 60 + sec;
            }, 0) /
            matches.length /
            60
          ).toFixed(1) + " min"
        : "0 min",
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-beige-50 to-mint-leaf-100 text-muted-teal-900 p-6 font-mono">
      {/* Navigation */}
      <nav className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold">Match History</h1>
        <div className="flex gap-3">
          <Link href="/">
            <button className="bg-mint-leaf-500 px-5 py-2 rounded-md hover:bg-mint-leaf-600 transition text-white">
              Home
            </button>
          </Link>
          <Link href="/live-game">
            <button className="bg-white border border-mint-leaf-500 px-5 py-2 rounded-md hover:bg-mint-leaf-50 transition text-muted-teal-900">
              Spectate
            </button>
          </Link>
          <Link href="/leaderboard">
            <button className="bg-mint-leaf-500 px-5 py-2 rounded-md hover:bg-mint-leaf-600 transition text-white">
              Leaderboard
            </button>
          </Link>
        </div>
      </nav>

      <main className="max-w-6xl mx-auto">
        {/* Statistics */}
        <section className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
          <div className="bg-white rounded-lg shadow p-4 border-l-4 border-mint-leaf-500">
            <p className="text-gray-600 text-sm">Total Matches</p>
            <p className="text-3xl font-bold">{stats.total}</p>
          </div>
          <div className="bg-white rounded-lg shadow p-4 border-l-4 border-blue-500">
            <p className="text-gray-600 text-sm">Claude Wins</p>
            <p className="text-3xl font-bold text-blue-600">
              {stats.claudeWins}
            </p>
          </div>
          <div className="bg-white rounded-lg shadow p-4 border-l-4 border-green-500">
            <p className="text-gray-600 text-sm">GPT Wins</p>
            <p className="text-3xl font-bold text-green-600">{stats.gptWins}</p>
          </div>
          <div className="bg-white rounded-lg shadow p-4 border-l-4 border-purple-500">
            <p className="text-gray-600 text-sm">Gemini Wins</p>
            <p className="text-3xl font-bold text-purple-600">
              {stats.geminiWins}
            </p>
          </div>
          <div className="bg-white rounded-lg shadow p-4 border-l-4 border-orange-500">
            <p className="text-gray-600 text-sm">Avg Duration</p>
            <p className="text-3xl font-bold text-orange-600">
              {stats.avgDuration}
            </p>
          </div>
        </section>

        {/* Filters */}
        <div className="mb-6 flex gap-2">
          {[
            { key: "all", label: "All Matches", color: "bg-mint-leaf-500" },
            { key: "claude", label: "Claude Wins", color: "bg-blue-500" },
            { key: "gpt", label: "GPT Wins", color: "bg-green-500" },
            { key: "gemini", label: "Gemini Wins", color: "bg-purple-500" },
          ].map(({ key, label, color }) => (
            <button
              key={key}
              onClick={() => setFilter(key as typeof filter)}
              className={`px-4 py-2 rounded-md font-bold transition ${
                filter === key
                  ? `${color} text-white`
                  : "bg-white text-muted-teal-900 border-2 border-mint-leaf-500 hover:bg-mint-leaf-50"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Error State */}
        {error && (
          <div className="bg-yellow-100 border-2 border-yellow-500 text-yellow-800 p-4 rounded-lg mb-6">
            <p className="font-bold">Note: {error}</p>
            <p className="text-sm">Showing sample data</p>
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <div className="text-center py-12">
            <p className="text-lg">Loading match history...</p>
          </div>
        )}

        {/* Matches List */}
        {!loading && (
          <section className="bg-white rounded-lg shadow-lg overflow-hidden">
            {filteredMatches.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-mint-leaf-500 text-white">
                    <tr>
                      <th className="px-6 py-3 text-left">AI Agent 1</th>
                      <th className="px-6 py-3 text-left">AI Agent 2</th>
                      <th className="px-6 py-3 text-center">Winner</th>
                      <th className="px-6 py-3 text-left">Format</th>
                      <th className="px-6 py-3 text-left">Duration</th>
                      <th className="px-6 py-3 text-left">Final Score</th>
                      <th className="px-6 py-3 text-left">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredMatches.length > 0 ? (
                      filteredMatches.map((match) => (
                        <tr
                          key={match.id}
                          className="border-b hover:bg-gray-50 transition"
                        >
                          <td className="px-6 py-4">{match.aiAgent1}</td>
                          <td className="px-6 py-4">{match.aiAgent2}</td>
                          <td className="px-6 py-4 text-center">
                            <span className="bg-green-100 text-green-800 px-3 py-1 rounded-full font-bold">
                              {match.winner}
                            </span>
                          </td>
                          <td className="px-6 py-4">{match.format}</td>
                          <td className="px-6 py-4">{match.duration}</td>
                          <td className="px-6 py-4 font-bold">
                            {match.finalScore}
                          </td>
                          <td className="px-6 py-4 text-gray-600">
                            {match.date}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={7} className="px-6 py-8 text-center">
                          <p className="text-gray-600">No matches found</p>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-8 text-center">
                <p className="text-gray-600">No matches found</p>
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
