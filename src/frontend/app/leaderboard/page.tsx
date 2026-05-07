"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

interface Player {
  rank: number;
  aiAgent: string;
  model: string;
  wins: number;
  losses: number;
  winRate: number;
  rating: number;
  totalMatches: number;
}

export default function LeaderBoard() {
  const [players, setPlayers] = useState<Player[]>([]);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState("standard");
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    fetchLeaderboard();
  }, [mode]);

  const fetchLeaderboard = async () => {
    try {
      setLoading(true);
      // Replace with your actual API endpoint
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8080"}/api/leaderboard?mode=${mode}`,
        {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
          },
          credentials: "include",
        },
      );

      if (!response.ok) {
        throw new Error("Failed to fetch leaderboard");
      }

      const data = await response.json();
      setPlayers(data.players || mockLeaderboard);
    } catch (err) {
      console.error("Error fetching leaderboard:", err);
      // Use mock data
      setPlayers(mockLeaderboard);
    } finally {
      setLoading(false);
    }
  };

  const filteredPlayers = players.filter((p) =>
    p.aiAgent.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-beige-50 to-mint-leaf-100 text-muted-teal-900 p-6 font-mono">
      {/* Navigation */}
      <nav className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold">Leaderboard</h1>
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
          <Link href="/match-history">
            <button className="bg-mint-leaf-500 px-5 py-2 rounded-md hover:bg-mint-leaf-600 transition text-white">
              Match History
            </button>
          </Link>
        </div>
      </nav>

      <main className="max-w-6xl mx-auto">
        {/* Filters */}
        <section className="mb-6 bg-white rounded-lg shadow p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-bold mb-2">Game Mode</label>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value)}
                className="w-full px-4 py-2 border-2 border-mint-leaf-500 rounded-md"
              >
                <option value="standard">Failed to implement...</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-bold mb-2">Search Bot</label>
              <input
                type="text"
                placeholder="Search username..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full px-4 py-2 border-2 border-mint-leaf-500 rounded-md"
              />
            </div>
          </div>
        </section>

        {/* Loading State */}
        {loading && (
          <div className="text-center py-12">
            <p className="text-lg">Loading leaderboard...</p>
          </div>
        )}

        {/* Leaderboard Table */}
        {!loading && (
          <section className="bg-white rounded-lg shadow-lg overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-mint-leaf-500 text-white">
                  <tr>
                    <th className="px-6 py-3 text-left">Rank</th>
                    <th className="px-6 py-3 text-left">AI Agent</th>
                    <th className="px-6 py-3 text-left">Model</th>
                    <th className="px-6 py-3 text-center">Rating</th>
                    <th className="px-6 py-3 text-center">Wins</th>
                    <th className="px-6 py-3 text-center">Losses</th>
                    <th className="px-6 py-3 text-center">Win Rate</th>
                    <th className="px-6 py-3 text-center">Total Matches</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPlayers.length > 0 ? (
                    filteredPlayers.map((player, index) => (
                      <tr
                        key={player.rank}
                        className={`border-b hover:bg-gray-50 transition ${
                          index % 2 === 0 ? "bg-gray-50" : "bg-white"
                        }`}
                      >
                        <td className="px-6 py-4">
                          <span className="font-bold text-lg">
                            {player.rank === 1 && "🥇"}
                            {player.rank === 2 && "🥈"}
                            {player.rank === 3 && "🥉"}
                            {player.rank > 3 && `#${player.rank}`}
                          </span>
                        </td>
                        <td className="px-6 py-4 font-semibold">
                          {player.aiAgent}
                        </td>
                        <td className="px-6 py-4">
                          <span
                            className={`px-2 py-1 rounded text-xs font-bold ${
                              player.model === "Anthropic"
                                ? "bg-blue-100 text-blue-800"
                                : player.model === "OpenAI"
                                  ? "bg-green-100 text-green-800"
                                  : "bg-purple-100 text-purple-800"
                            }`}
                          >
                            {player.model}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-center">
                          <span className="bg-mint-leaf-100 px-3 py-1 rounded-full font-bold">
                            {player.rating}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-center text-green-600 font-bold">
                          {player.wins}
                        </td>
                        <td className="px-6 py-4 text-center text-red-600 font-bold">
                          {player.losses}
                        </td>
                        <td className="px-6 py-4 text-center">
                          <span className="bg-blue-100 px-3 py-1 rounded-full">
                            {player.winRate}%
                          </span>
                        </td>{" "}
                        <td className="px-6 py-4 text-center font-semibold">
                          {player.totalMatches}
                        </td>{" "}
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={8} className="px-6 py-8 text-center">
                        <p className="text-gray-600">No AI agents found</p>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

// Mock data
const mockLeaderboard: Player[] = [
  {
    rank: 1,
    aiAgent: "Claude 3.5 Haiku",
    model: "Anthropic",
    wins: 145,
    losses: 23,
    winRate: 86.3,
    rating: 1850,
    totalMatches: 168,
  },
  {
    rank: 2,
    aiAgent: "GPT-4",
    model: "OpenAI",
    wins: 128,
    losses: 31,
    winRate: 80.5,
    rating: 1765,
    totalMatches: 159,
  },
  {
    rank: 3,
    aiAgent: "Gemini Pro",
    model: "Google",
    wins: 112,
    losses: 42,
    winRate: 72.7,
    rating: 1650,
    totalMatches: 154,
  },
  {
    rank: 4,
    aiAgent: "Claude 3 Opus",
    model: "Anthropic",
    wins: 98,
    losses: 38,
    winRate: 72.1,
    rating: 1620,
    totalMatches: 136,
  },
  {
    rank: 5,
    aiAgent: "GPT-3.5 Turbo",
    model: "OpenAI",
    wins: 87,
    losses: 45,
    winRate: 65.9,
    rating: 1540,
    totalMatches: 132,
  },
];
