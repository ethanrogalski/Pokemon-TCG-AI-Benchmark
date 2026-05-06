// app/live-game/[gameId]/page.tsx

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { io, Socket } from "socket.io-client";

interface SpectatorState {
  gameId: string;
  playerA: string;
  playerB: string;
  status: string;
  phase: string;
  duration: string;
  score: string;
  lastAction: string;
  events: string[];
}

const LIVE_WS = process.env.NEXT_PUBLIC_GAME_SERVER || "localhost:8080";

const initialState: SpectatorState = {
  gameId: "",
  playerA: "",
  playerB: "",
  status: "Loading",
  phase: "-",
  duration: "0:00",
  score: "0 - 0",
  lastAction: "Waiting for live updates...",
  events: [],
};

export default function SpectatorPage({
  params,
}: {
  params: { gameId: string };
}) {
  const { gameId } = params;

  const [state, setState] = useState<SpectatorState>({
    ...initialState,
    gameId,
  });

  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";

    const socket: Socket = io(`${protocol}//${LIVE_WS}`, {
      transports: ["websocket"],
      path: "/socket.io/",
    });

    socket.on("connect", () => {
      console.log("[spectator] connected");

      setConnected(true);
      setError(null);

      socket.emit("subscribe", {
        matchId: gameId,
      });
    });

    socket.on("game:update", (payload) => {
      if (payload.matchId !== gameId) return;

      setState((current) => ({
        ...current,
        playerA: payload.playerA ?? current.playerA,
        playerB: payload.playerB ?? current.playerB,
        status: payload.status ?? current.status,
        phase: payload.phase ?? current.phase,
        duration: payload.duration ?? current.duration,
        score: payload.score ?? current.score,
        lastAction: payload.lastAction ?? current.lastAction,
        events: payload.events ?? current.events,
      }));
    });

    socket.on("disconnect", () => {
      console.log("[spectator] disconnected");
      setConnected(false);
    });

    socket.on("connect_error", (err) => {
      console.error("[spectator] socket error", err);

      setConnected(false);
      setError("Unable to connect to live spectator stream.");
    });

    return () => {
      socket.disconnect();
    };
  }, [gameId]);

  return (
    <div className="min-h-screen bg-linear-to-br from-beige-50 to-mint-leaf-100 text-muted-teal-900 p-6 font-mono">
      <nav className="flex flex-wrap items-center justify-between gap-3 mb-8">
        <div className="space-y-1">
          <h1 className="text-3xl font-bold">Spectating Match {gameId}</h1>

          <p className="text-sm text-muted-teal-700">
            Real-time AI battle updates and action log.
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <Link href="/live-game">
            <button className="bg-mint-leaf-500 px-5 py-2 rounded-md hover:bg-mint-leaf-600 transition text-white">
              Back to Live Games
            </button>
          </Link>

          <Link href="/">
            <button className="bg-white border border-mint-leaf-500 px-5 py-2 rounded-md hover:bg-mint-leaf-50 transition text-muted-teal-900">
              Home
            </button>
          </Link>
        </div>
      </nav>

      <section className="grid gap-6 lg:grid-cols-[1.6fr_1fr] max-w-6xl mx-auto">
        <div className="rounded-3xl bg-white border border-gray-200 p-6 shadow-sm">
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.24em] text-muted-teal-500">
                  Match information
                </p>

                <h2 className="text-2xl font-bold text-muted-teal-900">
                  {state.playerA} vs {state.playerB}
                </h2>
              </div>

              <div
                className={`rounded-full px-4 py-2 text-sm font-semibold ${
                  connected
                    ? "bg-green-100 text-green-800"
                    : "bg-red-100 text-red-800"
                }`}
              >
                {connected ? "Live stream connected" : "Disconnected"}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              <div className="rounded-2xl bg-beige-50 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-muted-teal-500">
                  Phase
                </p>

                <p className="mt-2 text-lg font-semibold text-muted-teal-900">
                  {state.phase}
                </p>
              </div>

              <div className="rounded-2xl bg-beige-50 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-muted-teal-500">
                  Duration
                </p>

                <p className="mt-2 text-lg font-semibold text-muted-teal-900">
                  {state.duration}
                </p>
              </div>

              <div className="rounded-2xl bg-beige-50 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-muted-teal-500">
                  Score
                </p>

                <p className="mt-2 text-lg font-semibold text-muted-teal-900">
                  {state.score}
                </p>
              </div>
            </div>

            <div className="rounded-2xl bg-gray-50 p-4">
              <p className="text-sm font-semibold text-muted-teal-900">
                Latest action
              </p>

              <p className="mt-2 text-sm text-muted-teal-700">
                {state.lastAction}
              </p>
            </div>
          </div>
        </div>

        <aside className="rounded-3xl bg-white border border-gray-200 p-6 shadow-sm">
          <h3 className="text-xl font-bold text-muted-teal-900 mb-4">
            Event log
          </h3>

          <div className="space-y-3 max-h-120 overflow-y-auto pr-2">
            {state.events.length > 0 ? (
              state.events.map((event, index) => (
                <div
                  key={index}
                  className="rounded-2xl bg-beige-50 p-4 text-sm text-muted-teal-700"
                >
                  {event}
                </div>
              ))
            ) : (
              <div className="rounded-2xl bg-beige-50 p-4 text-sm text-muted-teal-700">
                Waiting for live match updates...
              </div>
            )}
          </div>
        </aside>
      </section>

      {error && (
        <div className="mt-6 rounded-xl bg-yellow-100 border border-yellow-300 p-4 text-yellow-800">
          <p className="font-semibold">Error:</p>
          <p>{error}</p>
        </div>
      )}
    </div>
  );
}
