import Link from "next/link";

const NAV_BUTTONS = [
  { label: "Play", href: "/play" },
  { label: "Leaderboard", href: "/leaderboard" },
  { label: "About", href: "/about" },
];

export default function HomepageName() {
  return (
    <div className="min-h-screen relative overflow-hidden font-sans">
      <div className="absolute inset-0 bg-beige-50" />
      <div
        className="absolute inset-0 opacity-10"
        style={{
          backgroundImage:
            "linear-gradient(rgba(93,162,129,.2) 1px, transparent 1px), linear-gradient(90deg, rgba(93,162,129,.2) 1px, transparent 1px)",
          backgroundSize: "32px 32px",
        }}
      />
      <div className="relative z-10 flex flex-col items-center justify-center min-h-screen p-6 gap-8">
        <h1 className="text-6xl md:text-8xl font-black text-muted-teal-900 tracking-wide drop-shadow-md text-center">
          Pokemon Battlegrounds
        </h1>

        <div className="w-full max-w-sm flex flex-col gap-3">
          {NAV_BUTTONS.map(({ label, href }) => (
            <Link
              key={label}
              href={href}
              className="w-full py-5 bg-mint-leaf-500 hover:bg-mint-leaf-600 active:translate-y-px text-muted-teal-900 text-xl font-bold rounded-lg shadow-md border-2 border-muted-teal-500 text-center transition-all duration-150"
            >
              {label}
            </Link>
          ))}
        </div>

        <p className="text-sm text-muted-teal-700">
          Choose your path, trainer.
        </p>
      </div>
    </div>
  );
}


