import React, { useState, useRef, useEffect } from "react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Rocket } from "lucide-react";
import { toast } from "sonner";

export default function Crash() {
  const { refresh } = useAuth();
  const [amount, setAmount] = useState(10);
  const [autoCashout, setAutoCashout] = useState(2.0);
  const [playing, setPlaying] = useState(false);
  const [displayMult, setDisplayMult] = useState(1.0);
  const [crashed, setCrashed] = useState(null); // {crash_point, won, payout, multiplier}
  const [history, setHistory] = useState([]);
  const rafRef = useRef(null);

  useEffect(() => () => cancelAnimationFrame(rafRef.current), []);

  const play = async () => {
    if (playing) return;
    setCrashed(null);
    setDisplayMult(1.0);
    setPlaying(true);
    try {
      const { data } = await api.post("/games/crash/play", {
        amount: Number(amount),
        auto_cashout: Number(autoCashout),
      });
      const crashPoint = data.details.crash_point;
      const target = Math.min(crashPoint, data.details.auto_cashout);
      // Animate from 1.00 to target/crashPoint over ~2s
      const final = data.result === "win" ? target : crashPoint;
      const dur = 1500 + Math.min(1500, final * 200);
      const start = performance.now();
      const tick = (now) => {
        const t = Math.min(1, (now - start) / dur);
        const cur = 1 + (final - 1) * t;
        setDisplayMult(cur);
        if (t < 1) {
          rafRef.current = requestAnimationFrame(tick);
        } else {
          setDisplayMult(final);
          setCrashed({
            crash_point: crashPoint,
            won: data.result === "win",
            payout: data.payout,
            multiplier: data.multiplier,
          });
          setHistory((h) => [{ crash: crashPoint, win: data.result === "win" }, ...h].slice(0, 12));
          setPlaying(false);
          refresh();
          if (data.result === "win") toast.success(`Cashed out at ${data.multiplier.toFixed(2)}x · +${data.payout.toFixed(2)}`);
          else toast.error(`Crashed at ${crashPoint.toFixed(2)}x`);
        }
      };
      rafRef.current = requestAnimationFrame(tick);
    } catch (e) {
      setPlaying(false);
      toast.error(formatApiError(e.response?.data?.detail) || "Bet failed");
    }
  };

  const isCrash = crashed && !crashed.won;
  const color = playing ? "text-bx-cyan" : isCrash ? "text-bx-red" : crashed?.won ? "text-bx-green" : "text-white";

  return (
    <div className="space-y-6" data-testid="crash-page">
      <div className="flex items-center gap-3">
        <Rocket className="text-bx-cyan" />
        <h1 className="font-display text-3xl font-black tracking-tight">Crash</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bx-card p-8 min-h-[360px] flex flex-col items-center justify-center relative overflow-hidden">
          <svg className="absolute inset-0 w-full h-full opacity-20" preserveAspectRatio="none" viewBox="0 0 100 100">
            <defs>
              <linearGradient id="g" x1="0" y1="1" x2="1" y2="0">
                <stop offset="0%" stopColor="#00E5FF" stopOpacity="0.0" />
                <stop offset="100%" stopColor="#00E5FF" stopOpacity="0.6" />
              </linearGradient>
            </defs>
            <path
              d={`M 0,100 Q ${30 + displayMult * 5},${100 - displayMult * 12} ${Math.min(100, 20 + displayMult * 15)},${Math.max(0, 100 - displayMult * 25)} L 100,100 Z`}
              fill="url(#g)"
            />
            <path
              d={`M 0,100 Q ${30 + displayMult * 5},${100 - displayMult * 12} ${Math.min(100, 20 + displayMult * 15)},${Math.max(0, 100 - displayMult * 25)}`}
              fill="none" stroke="#00E5FF" strokeWidth="0.5"
            />
          </svg>
          <div className={`relative font-display font-black text-7xl lg:text-8xl tabular-nums ${color} ${playing ? "bx-text-glow" : ""}`} data-testid="crash-multiplier-display">
            {displayMult.toFixed(2)}x
          </div>
          {isCrash && (
            <div className="relative mt-2 font-display text-xl text-bx-red uppercase tracking-widest">Crashed!</div>
          )}
          {crashed?.won && (
            <div className="relative mt-2 font-display text-lg text-bx-green uppercase tracking-widest">Cashed Out</div>
          )}
        </div>

        <div className="bx-card p-6 space-y-5">
          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">Bet Amount</label>
            <Input
              type="number" min="1" step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="bg-[#0B1121] border-[#1E293B] focus-visible:ring-bx-cyan h-11 font-mono"
              disabled={playing}
              data-testid="crash-amount-input"
            />
            <div className="flex gap-2">
              {[0.5, 2, 10].map((m) => (
                <button
                  key={m}
                  onClick={() => setAmount((a) => Math.max(1, Math.round(Number(a) * m * 100) / 100))}
                  disabled={playing}
                  className="text-xs px-3 py-1 rounded bg-[#0B1121] border border-[#1E293B] hover:border-bx-cyan/40 disabled:opacity-50"
                  data-testid={`crash-amount-multiplier-${m}`}
                >
                  {m === 0.5 ? "½" : `${m}x`}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">Auto Cashout</label>
            <Input
              type="number" min="1.01" step="0.01"
              value={autoCashout}
              onChange={(e) => setAutoCashout(e.target.value)}
              className="bg-[#0B1121] border-[#1E293B] focus-visible:ring-bx-cyan h-11 font-mono"
              disabled={playing}
              data-testid="crash-cashout-input"
            />
          </div>

          <Button
            onClick={play}
            disabled={playing}
            className="w-full h-12 bg-bx-cyan text-[#0B1121] hover:bg-bx-cyan/90 font-display font-bold tracking-wider hover:shadow-[0_0_24px_rgba(0,229,255,0.5)] transition-all"
            data-testid="crash-bet-button"
          >
            {playing ? "ROLLING…" : "PLACE BET"}
          </Button>

          <div className="text-xs text-bx-muted text-center">
            Profit on win: <span className="text-bx-gold font-mono font-bold">+{(amount * autoCashout - amount).toFixed(2)}</span>
          </div>
        </div>
      </div>

      <div className="bx-card p-4">
        <div className="text-xs uppercase tracking-wider text-bx-muted mb-3 font-bold">Recent Crashes</div>
        <div className="flex gap-2 flex-wrap" data-testid="crash-history">
          {history.length === 0 && <div className="text-xs text-bx-muted">No rounds yet</div>}
          {history.map((h, i) => (
            <div
              key={i}
              className={`px-3 py-1.5 rounded text-xs font-mono font-bold border ${
                h.crash >= 2 ? "border-bx-green/40 text-bx-green bg-bx-green/5" : "border-bx-red/40 text-bx-red bg-bx-red/5"
              }`}
            >
              {h.crash.toFixed(2)}x
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
