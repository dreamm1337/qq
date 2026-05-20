import React from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Rocket, Bomb, Coins, CircleDot, Building2, Circle, Target, Spade } from "lucide-react";

const GAMES = [
  { slug: "crash",     name: "Crash",     tag: "Manual cashout", icon: Rocket,     accent: "from-bx-cyan/30 to-transparent",   img: "https://static.prod-images.emergentagent.com/jobs/c7607b06-42ba-46b8-9205-884ba3fb593b/images/637cf48d60bc51493f19574d76a969996a491579bb3a026f7b525fdbf550817c.png" },
  { slug: "mines",     name: "Mines",     tag: "Reveal & cash",  icon: Bomb,       accent: "from-bx-purple/30 to-transparent", img: "https://static.prod-images.emergentagent.com/jobs/c7607b06-42ba-46b8-9205-884ba3fb593b/images/661975a42151e130f50bc1ffedd633e14583014f721d518e9b7d14acbee69162.png" },
  { slug: "towers",    name: "Towers",    tag: "Climb to win",   icon: Building2,  accent: "from-bx-cyan/30 to-transparent" },
  { slug: "plinko",    name: "Plinko",    tag: "Drop the ball",  icon: Circle,     accent: "from-bx-gold/30 to-transparent" },
  { slug: "blackjack", name: "Blackjack", tag: "Beat the dealer",icon: Spade,      accent: "from-bx-green/30 to-transparent" },
  { slug: "upgrader",  name: "Upgrader",  tag: "Target multi",   icon: Target,     accent: "from-bx-red/30 to-transparent" },
  { slug: "coinflip",  name: "Coinflip",  tag: "Quick 1.95x",    icon: Coins,      accent: "from-bx-gold/30 to-transparent",   img: "https://static.prod-images.emergentagent.com/jobs/c7607b06-42ba-46b8-9205-884ba3fb593b/images/3de2e14937345deee009a817522472e885b37fc35855923c18950eee2adb97e4.png" },
  { slug: "roulette",  name: "Roulette",  tag: "2x · 2x · 14x",  icon: CircleDot,  accent: "from-bx-red/30 to-transparent",    img: "https://static.prod-images.emergentagent.com/jobs/c7607b06-42ba-46b8-9205-884ba3fb593b/images/0a47c02fbf01b6d0a34f5b54a2c0b7bf9a05cdcad17e704aa528b9a95d4aae6c.png" },
];

export default function Lobby() {
  const { user } = useAuth();
  return (
    <div className="space-y-10" data-testid="lobby-page">
      <section className="relative overflow-hidden bx-card p-8 lg:p-12">
        <div className="absolute inset-0 opacity-60 pointer-events-none"
          style={{
            backgroundImage: `url("https://static.prod-images.emergentagent.com/jobs/c7607b06-42ba-46b8-9205-884ba3fb593b/images/2f71c3261511aadb565681789736d502fbeebe63f7ef227c5e4acbe62812136e.png")`,
            backgroundSize: "cover", backgroundPosition: "center",
          }}
        />
        <div className="absolute inset-0 bg-gradient-to-r from-[#0B1121] via-[#0B1121]/80 to-transparent" />
        <div className="relative max-w-xl">
          <div className="text-xs uppercase tracking-[0.3em] text-bx-cyan font-bold mb-3">welcome back</div>
          <h1 className="font-display font-black text-4xl sm:text-5xl lg:text-6xl tracking-tighter">
            Hey, <span className="text-bx-cyan bx-text-glow">{user?.username}</span>
          </h1>
          <p className="mt-3 text-bx-muted max-w-md">
            8 fast-paced games with your demo balance. Crash, Mines, Towers, Plinko, Blackjack, Upgrader, Coinflip, Roulette.
          </p>
          <div className="mt-6 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#131A2A] border border-[#1E293B]">
            <span className="text-xs uppercase tracking-wider text-bx-muted">Balance</span>
            <span className="font-mono font-bold text-bx-gold">{Number(user?.balance || 0).toFixed(2)}</span>
          </div>
        </div>
      </section>

      <section>
        <div className="flex items-baseline justify-between mb-5">
          <h2 className="font-display text-xl font-bold tracking-tight">Games</h2>
          <span className="text-xs text-bx-muted uppercase tracking-wider">{GAMES.length} games</span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-4 sm:gap-5">
          {GAMES.map((g) => {
            const Icon = g.icon;
            return (
              <Link
                key={g.slug}
                to={`/${g.slug}`}
                data-testid={`game-card-${g.slug}`}
                className="group relative overflow-hidden bx-card bx-card-hover h-48"
              >
                <div className="absolute inset-0">
                  {g.img ? (
                    <img src={g.img} alt={g.name} className="w-full h-full object-cover opacity-90 group-hover:scale-110 transition-transform duration-700" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center"
                         style={{ background: "radial-gradient(circle at 30% 30%, rgba(0,229,255,0.15), transparent 60%), radial-gradient(circle at 70% 70%, rgba(176,38,255,0.15), transparent 60%), #131A2A" }}>
                      <Icon size={72} className="text-bx-cyan/40 group-hover:text-bx-cyan/80 transition-colors duration-500" strokeWidth={1.2} />
                    </div>
                  )}
                  <div className={`absolute inset-0 bg-gradient-to-t ${g.accent} via-[#131A2A]/50 to-[#131A2A]`} />
                </div>
                <div className="relative h-full flex flex-col justify-end p-4">
                  <div className="text-[10px] uppercase tracking-[0.25em] text-bx-cyan font-bold">{g.tag}</div>
                  <div className="font-display font-black text-xl sm:text-2xl tracking-tight mt-1">{g.name}</div>
                </div>
              </Link>
            );
          })}
        </div>
      </section>
    </div>
  );
}
