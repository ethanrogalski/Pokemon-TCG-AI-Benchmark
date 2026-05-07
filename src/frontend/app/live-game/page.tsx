"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { io, Socket } from "socket.io-client";

interface LiveGame {
  id: string;
  playerA: string;
  playerB: string;
  status: string;
  phase: string;
  startedAt: string;
  duration: string;
  watchers: number;
  score: string;
  lastAction: string;
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8080";
const LIVE_WS = process.env.NEXT_PUBLIC_GAME_SERVER || "localhost:8080";

const mockLiveGames: LiveGame[] = [
  {
    id: "4521",
    playerA: "Claude 3.5 Haiku",
    playerB: "GPT-4",
    status: "In Progress",
    phase: "Battle Phase",
    startedAt: "2m ago",
    duration: "08:42",
    watchers: 12,
    score: "4 - 3",
    lastAction: "Claude attached Lightning Energy to Active",
  },
  {
    id: "4487",
    playerA: "Gemini Pro",
    playerB: "Claude 3 Opus",
    status: "In Progress",
    phase: "Draw Step",
    startedAt: "5m ago",
    duration: "12:17",
    watchers: 9,
    score: "2 - 2",
    lastAction: "Gemini drew a card",
  },
  {
    id: "4499",
    playerA: "GPT-4",
    playerB: "Simple Bot",
    status: "Watching",
    phase: "Setup",
    startedAt: "1m ago",
    duration: "03:21",
    watchers: 21,
    score: "0 - 0",
    lastAction: "GPT-4 placed Active Basic Pokemon",
  },
];

export default function LiveGamePage() {
  const [liveGames, setLiveGames] = useState<LiveGame[]>([]);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchLiveGames = async () => {
      try {
        setLoading(true);
        const response = await fetch(`${API_BASE}/api/live-games`, {
          method: "GET",
          headers: { "Content-Type": "application/json" },
        });

        if (!response.ok) {
          throw new Error(`Unable to load live games (${response.status})`);
        }

        const data = await response.json();
        setLiveGames(data.games || mockLiveGames);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Could not load live games",
        );
        setLiveGames(mockLiveGames);
      } finally {
        setLoading(false);
      }
    };

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket: Socket = io(`${protocol}//${LIVE_WS}`, {
      transports: ["websocket"],
      path: "/socket.io/",
    });

    socket.on("connect", () => {
      setConnected(true);
      setError(null);
      socket.emit("subscribe", { topic: "live-games" });
    });

    socket.on("live-games:update", (payload: { games: LiveGame[] }) => {
      if (Array.isArray(payload.games)) {
        setLiveGames(payload.games);
      }
    });

    socket.on("disconnect", () => {
      setConnected(false);
    });

    socket.on("connect_error", (err) => {
      setConnected(false);
      setError("Could not connect to live game stream.");
      console.error("Socket.IO error:", err);
    });

    fetchLiveGames();

    return () => socket.disconnect();
  }, []);

  return (
    <div className="min-h-screen bg-linear-to-br from-beige-50 to-mint-leaf-100 text-muted-teal-900 p-6 font-mono">
      <nav className="flex flex-wrap items-center justify-between gap-3 mb-8">
        <div>
          <h1 className="text-3xl font-bold">Live Games</h1>
          <p className="text-sm text-muted-teal-700">
            Browse active AI matches and spectate live play.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link href="/">
            <button className="bg-mint-leaf-500 px-5 py-2 rounded-md hover:bg-mint-leaf-600 transition text-white">
              Home
            </button>
          </Link>
          <Link href="/live-game">
            <button className="bg-white border border-mint-leaf-500 px-5 py-2 rounded-md hover:bg-mint-leaf-50 transition text-muted-teal-900">
              Match History
            </button>
          </Link>
          <Link href="/leaderboard">
            <button className="bg-mint-leaf-500 px-5 py-2 rounded-md hover:bg-mint-leaf-600 transition text-white">
              Leaderboard
            </button>
          </Link>
        </div>
      </nav>

      <section className="mb-8 rounded-xl bg-white border border-mint-leaf-200 p-6 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <p className="text-sm text-muted-teal-700 mb-1">Live feed status</p>
            <p
              className={`font-semibold ${connected ? "text-green-700" : "text-red-700"}`}
            >
              {connected
                ? "Connected to live stream"
                : "Offline or unavailable"}
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <span className="rounded-full bg-mint-leaf-500 px-4 py-2 text-white">
              Live
            </span>
            <span className="rounded-full bg-mint-leaf-500 px-4 py-2 text-white">
              Spectator mode
            </span>
            <span className="rounded-full bg-orange-50 px-4 py-2 text-orange-700">
              AI battles
            </span>
          </div>
        </div>
        {error && (
          <div className="mt-4 rounded-lg bg-yellow-100 border border-yellow-300 p-4 text-yellow-800">
            <p className="font-semibold">Warning:</p>
            <p>{error}</p>
          </div>
        )}
      </section>

      <main className="max-w-6xl mx-auto">
        <section className="grid gap-4">
          {loading ? (
            <div className="rounded-xl bg-white border border-gray-200 p-8 text-center text-muted-teal-700 shadow-sm">
              Fetching live games...
            </div>
          ) : liveGames.length === 0 ? (
            <div className="rounded-xl bg-white border border-gray-200 p-8 text-center text-muted-teal-700 shadow-sm">
              <p className="font-semibold">No live battles available.</p>
              <p className="mt-2 text-sm">
                Start a match or try again shortly.
              </p>
            </div>
          ) : (
            liveGames.map((game) => (
              <div
                key={game.id}
                className="rounded-3xl bg-white border border-gray-200 p-6 shadow-sm hover:shadow-md transition"
              >
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  <div>
                    <p className="text-sm uppercase tracking-[0.2em] text-muted-teal-500">
                      Match ID {game.id}
                    </p>
                    <h2 className="text-2xl font-bold text-muted-teal-900">
                      {game.playerA} vs {game.playerB}
                    </h2>
                    <p className="mt-2 text-sm text-muted-teal-700 max-w-2xl">
                      {game.lastAction}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <span className="rounded-full bg-green-50 px-4 py-2 text-green-800">
                      {game.status}
                    </span>
                    <span className="rounded-full bg-blue-50 px-4 py-2 text-blue-800">
                      {game.phase}
                    </span>
                    <span className="rounded-full bg-orange-50 px-4 py-2 text-orange-800">
                      {game.watchers} viewers
                    </span>
                  </div>
                </div>

                <div className="mt-6 grid gap-4 sm:grid-cols-2">
                  <div className="rounded-2xl bg-beige-50 p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-muted-teal-500">
                      Duration
                    </p>
                    <p className="mt-2 text-lg font-semibold text-muted-teal-900">
                      {game.duration}
                    </p>
                  </div>
                  <div className="rounded-2xl bg-beige-50 p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-muted-teal-500">
                      Score
                    </p>
                    <p className="mt-2 text-lg font-semibold text-muted-teal-900">
                      {game.score}
                    </p>
                  </div>
                </div>

                <div className="mt-6 flex flex-wrap gap-3">
                  <Link href={`/live-game/${game.id}`}>
                    <button className="rounded-full bg-mint-leaf-500 px-5 py-3 font-semibold text-white hover:bg-mint-leaf-600 transition">
                      Spectate
                    </button>
                  </Link>
                  <button
                    onClick={() => navigator.clipboard.writeText(game.id)}
                    className="rounded-full border border-muted-teal-500 px-5 py-3 font-semibold text-muted-teal-900 hover:bg-muted-teal-50 transition"
                  >
                    Copy Match ID
                  </button>
                </div>
              </div>
            ))
          )}
        </section>
      </main>
    </div>
  );
}
