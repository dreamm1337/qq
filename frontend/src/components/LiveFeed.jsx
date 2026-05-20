import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Rocket, Bomb, Coins, CircleDot } from "lucide-react";

const ICONS = {
  crash: Rocket,
  mines: Bomb,
  coinflip: Coins,
  roulette: CircleDot,
};

export default function LiveFeed() {
  const [bets, setBets] = useState([]);

  const load = async () => {
    try {
      const { data } = await api.get("/bets/feed");
      setBets(data);
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, []);

  return (
    <aside
      className="hidden lg:flex flex-col fixed inset-y-0 right-0 w-[320px] pt-16 border-l border-[#1E293B] bg-[#0B1121] z-10"
      data-testid="live-feed"
    >
      <div className="px-5 py-4 border-b border-[#1E293B]">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full rounded-full bg-bx-green opacity-75 animate-ping" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-bx-green" />
          </span>
          <h3 className="font-display text-xs uppercase tracking-[0.25em] text-bx-muted">Live Bets</h3>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
        {bets.length === 0 && (
          <div className="text-center text-xs text-bx-muted py-8">No bets yet. Be the first!</div>
        )}
        {bets.map((b) => {
          const Icon = ICONS[b.game] || CircleDot;
          const win = b.result === "win";
          return (
            <div
              key={b.id}
              className="flex items-center gap-3 px-3 py-2 rounded-lg bg-[#131A2A] border border-[#1E293B] animate-rise"
              data-testid="feed-item"
            >
              <Icon size={16} className={win ? "text-bx-green" : "text-bx-red"} />
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium truncate">{b.username}</div>
                <div className="text-[10px] uppercase tracking-wider text-bx-muted">{b.game}</div>
              </div>
              <div className="text-right">
                <div className={`font-mono text-xs font-bold ${win ? "text-bx-green" : "text-bx-red"}`}>
                  {win ? "+" : "-"}{(win ? b.payout - b.amount : b.amount).toFixed(2)}
                </div>
                <div className="text-[10px] text-bx-muted font-mono">{b.multiplier.toFixed(2)}x</div>
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}
