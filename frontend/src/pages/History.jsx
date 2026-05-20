import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Rocket, Bomb, Coins, CircleDot } from "lucide-react";

const ICONS = { crash: Rocket, mines: Bomb, coinflip: Coins, roulette: CircleDot };

export default function History() {
  const [bets, setBets] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/bets/me");
        setBets(data);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const totalWagered = bets.reduce((s, b) => s + b.amount, 0);
  const totalWon = bets.reduce((s, b) => s + b.payout, 0);
  const net = totalWon - totalWagered;

  return (
    <div className="space-y-6" data-testid="history-page">
      <h1 className="font-display text-3xl font-black tracking-tight">My History</h1>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bx-card p-5">
          <div className="text-xs uppercase tracking-wider text-bx-muted font-bold">Total Wagered</div>
          <div className="font-mono font-bold text-2xl mt-1">{totalWagered.toFixed(2)}</div>
        </div>
        <div className="bx-card p-5">
          <div className="text-xs uppercase tracking-wider text-bx-muted font-bold">Total Won</div>
          <div className="font-mono font-bold text-2xl mt-1 text-bx-gold">{totalWon.toFixed(2)}</div>
        </div>
        <div className="bx-card p-5">
          <div className="text-xs uppercase tracking-wider text-bx-muted font-bold">Net P/L</div>
          <div className={`font-mono font-bold text-2xl mt-1 ${net >= 0 ? "text-bx-green" : "text-bx-red"}`}>
            {net >= 0 ? "+" : ""}{net.toFixed(2)}
          </div>
        </div>
      </div>

      <div className="bx-card overflow-hidden">
        <div className="px-6 py-4 border-b border-[#1E293B]">
          <div className="font-display text-sm font-bold uppercase tracking-wider">Recent Bets</div>
        </div>
        <div className="divide-y divide-[#1E293B]">
          {loading && <div className="p-6 text-bx-muted text-sm">Loading…</div>}
          {!loading && bets.length === 0 && <div className="p-6 text-bx-muted text-sm">No bets yet.</div>}
          {bets.map((b) => {
            const Icon = ICONS[b.game] || CircleDot;
            const win = b.result === "win";
            return (
              <div key={b.id} className="flex items-center gap-4 px-6 py-3 hover:bg-[#0B1121]/40" data-testid="history-row">
                <Icon size={18} className={win ? "text-bx-green" : "text-bx-red"} />
                <div className="flex-1 min-w-0">
                  <div className="font-display text-sm capitalize">{b.game}</div>
                  <div className="text-[11px] text-bx-muted font-mono">{new Date(b.created_at).toLocaleString()}</div>
                </div>
                <div className="text-xs font-mono text-bx-muted">{b.amount.toFixed(2)}</div>
                <div className={`text-sm font-mono font-bold w-24 text-right ${win ? "text-bx-green" : "text-bx-red"}`}>
                  {win ? "+" : "-"}{(win ? b.payout - b.amount : b.amount).toFixed(2)}
                </div>
                <div className="text-xs font-mono text-bx-muted w-16 text-right">{b.multiplier.toFixed(2)}x</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
