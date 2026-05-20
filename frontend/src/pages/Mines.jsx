import React, { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Bomb, Gem } from "lucide-react";
import { toast } from "sonner";

export default function Mines() {
  const { refresh } = useAuth();
  const [amount, setAmount] = useState(10);
  const [mines, setMines] = useState(3);
  const [picks, setPicks] = useState([]); // tile indices
  const [revealed, setRevealed] = useState({}); // {idx: 'gem'|'bomb'}
  const [playing, setPlaying] = useState(false);
  const [result, setResult] = useState(null);

  const togglePick = (idx) => {
    if (playing) return;
    if (Object.keys(revealed).length > 0) {
      setRevealed({});
      setResult(null);
    }
    setPicks((p) => (p.includes(idx) ? p.filter((x) => x !== idx) : [...p, idx]));
  };

  const play = async () => {
    if (picks.length === 0) {
      toast.error("Pick at least one tile");
      return;
    }
    setPlaying(true);
    setRevealed({});
    setResult(null);
    try {
      const { data } = await api.post("/games/mines/play", {
        amount: Number(amount),
        mines: Number(mines),
        picks,
      });
      const bombsSet = new Set(data.details.bombs);
      // Reveal picks first, then bombs after small delay
      const map = {};
      data.details.picks.forEach((p) => {
        map[p] = bombsSet.has(p) ? "bomb" : "gem";
      });
      // Also show remaining bombs
      data.details.bombs.forEach((b) => {
        if (map[b] === undefined) map[b] = "bomb-shown";
      });
      setRevealed(map);
      setResult(data);
      refresh();
      if (data.result === "win") {
        toast.success(`Won ${data.payout.toFixed(2)} at ${data.multiplier.toFixed(2)}x`);
      } else {
        toast.error("Boom! You hit a mine");
      }
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Bet failed");
    } finally {
      setPlaying(false);
    }
  };

  const clear = () => {
    if (playing) return;
    setPicks([]);
    setRevealed({});
    setResult(null);
  };

  return (
    <div className="space-y-6" data-testid="mines-page">
      <div className="flex items-center gap-3">
        <Bomb className="text-bx-purple" />
        <h1 className="font-display text-3xl font-black tracking-tight">Mines</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bx-card p-6">
          <div className="grid grid-cols-5 gap-2 sm:gap-3 max-w-xl mx-auto">
            {Array.from({ length: 25 }, (_, i) => {
              const isPicked = picks.includes(i);
              const rev = revealed[i];
              const base = "aspect-square rounded-lg flex items-center justify-center text-2xl transition-all duration-200 border-2";
              let cls = `${base} bg-[#0B1121] border-[#1E293B] hover:border-bx-cyan/50 cursor-pointer`;
              if (isPicked && !rev) cls = `${base} bg-bx-cyan/10 border-bx-cyan/60 cursor-pointer`;
              if (rev === "gem") cls = `${base} bg-bx-green/15 border-bx-green/60`;
              if (rev === "bomb") cls = `${base} bg-bx-red/20 border-bx-red/70 animate-pulse-neon`;
              if (rev === "bomb-shown") cls = `${base} bg-bx-red/5 border-bx-red/30 opacity-50`;
              return (
                <button
                  key={i}
                  onClick={() => togglePick(i)}
                  disabled={playing}
                  className={cls}
                  data-testid={`mines-tile-${i}`}
                >
                  {rev === "gem" && <Gem size={22} className="text-bx-green" />}
                  {(rev === "bomb" || rev === "bomb-shown") && <Bomb size={22} className="text-bx-red" />}
                </button>
              );
            })}
          </div>
        </div>

        <div className="bx-card p-6 space-y-5">
          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">Bet Amount</label>
            <Input
              type="number" min="1" step="0.01" value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="bg-[#0B1121] border-[#1E293B] focus-visible:ring-bx-cyan h-11 font-mono"
              disabled={playing}
              data-testid="mines-amount-input"
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">Mines (1-24)</label>
            <Input
              type="number" min="1" max="24" value={mines}
              onChange={(e) => setMines(e.target.value)}
              className="bg-[#0B1121] border-[#1E293B] focus-visible:ring-bx-cyan h-11 font-mono"
              disabled={playing}
              data-testid="mines-count-input"
            />
          </div>

          <div className="text-xs text-bx-muted">
            Selected tiles: <span className="text-white font-mono font-bold">{picks.length}</span>
          </div>

          <Button
            onClick={play}
            disabled={playing || picks.length === 0}
            className="w-full h-12 bg-bx-cyan text-[#0B1121] hover:bg-bx-cyan/90 font-display font-bold tracking-wider hover:shadow-[0_0_24px_rgba(0,229,255,0.5)] transition-all disabled:opacity-50"
            data-testid="mines-bet-button"
          >
            {playing ? "ROLLING…" : "REVEAL"}
          </Button>

          <Button
            variant="outline"
            onClick={clear}
            disabled={playing}
            className="w-full bg-transparent border-[#1E293B] hover:bg-[#0B1121] hover:border-bx-muted"
            data-testid="mines-clear-button"
          >
            Clear
          </Button>

          {result && (
            <div className={`text-center font-display text-sm font-bold ${result.result === "win" ? "text-bx-green" : "text-bx-red"}`} data-testid="mines-result">
              {result.result === "win"
                ? `+${result.payout.toFixed(2)} @ ${result.multiplier.toFixed(2)}x`
                : "BUSTED"}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
