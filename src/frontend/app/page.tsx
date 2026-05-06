const GAME_ENGINE_BASE = "http://localhost:4200";

const NAV_BUTTONS = [
  {
    label: "Play",
    href: `${GAME_ENGINE_BASE}/games`,
    description: "Challenge an AI agent to a match",
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-7 h-7">
        <path d="M8 5.14v14l11-7-11-7z" />
      </svg>
    ),
  },
  {
    label: "Match History",
    href: `${GAME_ENGINE_BASE}/games/history`,
    description: "Review your past battles and replays",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-7 h-7">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    label: "Live Game",
    href: `${GAME_ENGINE_BASE}/games/active`,
    description: "Spectate games happening right now",
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-7 h-7">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2a10 10 0 100 20A10 10 0 0012 2zm0 18a8 8 0 110-16 8 8 0 010 16z" opacity="0.3"/>
        <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2"/>
      </svg>
    ),
  },
];

const STATS = [
  { value: "AI", label: "Powered" },
  { value: "PTCG", label: "Engine" },
  { value: "Live", label: "Matches" },
];

export default function HomePage() {
  return (
    <div className="min-h-screen relative overflow-hidden font-sans">
      {/* Base background */}
      <div className="absolute inset-0 bg-beige-50" />

      {/* Radial glow */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 70% 50% at 50% 0%, rgba(61,194,158,0.13) 0%, transparent 70%)",
        }}
      />

      {/* Dot grid */}
      <div
        className="absolute inset-0 opacity-25 pointer-events-none"
        style={{
          backgroundImage:
            "radial-gradient(circle, rgba(93,162,129,0.5) 1px, transparent 1px)",
          backgroundSize: "28px 28px",
        }}
      />

      {/* Page layout */}
      <div className="relative z-10 flex flex-col items-center justify-center min-h-screen px-6 py-16 gap-10">

        {/* Badge */}
        <div className="flex items-center gap-2 px-4 py-1.5 rounded-full border border-muted-teal-500 bg-beige-50/80 backdrop-blur-sm">
          <span className="w-2 h-2 rounded-full bg-celadon-500 animate-pulse" />
          <span className="text-xs font-semibold tracking-widest uppercase text-muted-teal-700">
            Pokémon TCG · AI Arena
          </span>
        </div>

        {/* Title */}
        <div className="text-center space-y-3">
          <h1 className="text-7xl md:text-9xl font-black text-muted-teal-900 tracking-tight leading-none">
            Agent
            <span className="text-mint-leaf-500">-PT</span>
          </h1>
          <p className="text-base md:text-lg text-muted-teal-700 max-w-sm mx-auto leading-relaxed">
            Play, watch, and study Pokémon TCG matches powered by autonomous AI agents.
          </p>
        </div>

        {/* Stat strip */}
        <div className="flex items-center gap-6">
          {STATS.map(({ value, label }, i) => (
            <div key={label} className="flex items-center gap-6">
              <div className="text-center">
                <div className="text-xl font-black text-mint-leaf-500">{value}</div>
                <div className="text-xs text-muted-teal-700 uppercase tracking-wider">{label}</div>
              </div>
              {i < STATS.length - 1 && (
                <div className="w-px h-8 bg-muted-teal-500 opacity-40" />
              )}
            </div>
          ))}
        </div>

        {/* Nav cards */}
        <div className="w-full max-w-md flex flex-col gap-3">
          {NAV_BUTTONS.map(({ label, href, description, icon }) => (
            <a
              key={label}
              href={href}
              className="group flex items-center gap-4 w-full px-5 py-4 bg-mint-leaf-500 hover:bg-mint-leaf-600 border-2 border-muted-teal-500 rounded-xl shadow-md hover:shadow-lg hover:-translate-y-0.5 active:translate-y-0 transition-all duration-150 text-left"
            >
              <span className="flex-shrink-0 text-muted-teal-900 opacity-80 group-hover:opacity-100 transition-opacity">
                {icon}
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-lg font-bold text-muted-teal-900 leading-tight">{label}</div>
                <div className="text-xs text-muted-teal-700 mt-0.5 truncate">{description}</div>
              </div>
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2.5}
                className="w-4 h-4 text-muted-teal-700 flex-shrink-0 group-hover:translate-x-0.5 transition-transform"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            </a>
          ))}
        </div>

        {/* Footer */}
        <p className="text-xs text-muted-teal-700 opacity-60 tracking-wide">
          Built on the Twinleaf engine · Local instance
        </p>
      </div>
    </div>
  );
}
