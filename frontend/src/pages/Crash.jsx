import React, { useState, useRef, useEffect, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Rocket } from "lucide-react";
import { toast } from "sonner";

const GROWTH = 0.18;
const multAt = (ms) => Math.exp((ms / 1000) * GROWTH);

export default function Crash() {
  const { refresh } = useAuth();
  const [amount, setAmount] = useState(10);
  const [autoCashout, setAutoCashout] = useState(""); // empty = manual only
  const [phase, setPhase] = useState("idle"); // idle | playing | cashed | crashed
  const [displayMult, setDisplayMult] = useState(1.0);
  const [history, setHistory] = useState([]);
  const [lastWin, setLastWin] = useState(null);
  const gameRef = useRef(null); // {game_id, crashPoint, startLocal, autoCashout}
  const rafRef = useRef(null);
  const cashedRef = useRef(false);

  useEffect(() => () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
  }, []);

  const cashoutNow = useCallback(async () => {
    if (cashedRef.current || !gameRef.current) return;
    cashedRef.current = true;
    try {
      const { data } = await api.post("/games/crash/cashout", { game_id: gameRef.current.game_id });
      if (data.result === "win") {
        setPhase("cashed");
        setLastWin({ mult: data.multiplier, payout: data.payout });
        toast.success(`Cashed at ${data.multiplier.toFixed(2)}x · +${data.payout.toFixed(2)}`);
      } else {
        setPhase("crashed");
        toast.error("Crashed before cashout!");
      }
      refresh();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Cashout failed");
    }
  }, [refresh]);

  const tick = useCallback(() => {
    const g = gameRef.current;
    if (!g) return;
    const elapsed = Date.now() - g.startLocal;
    const m = Math.min(multAt(elapsed), g.crashPoint);
    setDisplayMult(m);

    // Auto-cashout
    if (!cashedRef.current && g.autoCashout && m >= g.autoCashout) {
      cashoutNow();
      return;
    }

    // Crashed without cashout
    if (m >= g.crashPoint) {
      if (!cashedRef.current) {
        cashedRef.current = true;
        setPhase("crashed");
        setHistory((h) => [{ crash: g.crashPoint, win: false }, ...h].slice(0, 14));
        // Tell server (best-effort)
        api.post("/games/crash/bust", { game_id: g.game_id }).catch(() => {});
        refresh();
        toast.error(`Crashed at ${g.crashPoint.toFixed(2)}x`);
      }
      return;
    }
    rafRef.current = requestAnimationFrame(tick);
  }, [cashoutNow, refresh]);

  const place = async () => {
    if (phase === "playing") return;
    setDisplayMult(1.0);
    setLastWin(null);
    setPhase("playing");
    cashedRef.current = false;
    try {
      const body = { amount: Number(amount) };
      if (autoCashout && Number(autoCashout) > 1) body.auto_cashout = Number(autoCashout);
      const { data } = await api.post("/games/crash/start", body);
      gameRef.current = {
        game_id: data.game_id,
        crashPoint: data.crash_point,
        startLocal: Date.now(),
        autoCashout: data.auto_cashout || null,
      };
      // After cashout settles, push to history once we end
      const _pushHistoryOnEnd = () => {
        if (cashedRef.current) {
          setHistory((h) => [{ crash: data.crash_point, win: phase === "cashed" }, ...h].slice(0, 14));
        }
      };
      void _pushHistoryOnEnd;
      refresh();
      rafRef.current = requestAnimationFrame(tick);
    } catch (e) {
      setPhase("idle");
      toast.error(formatApiError(e.response?.data?.detail) || "Bet failed");
    }
  };

  // When phase becomes cashed, also record history
  useEffect(() => {
    if (phase === "cashed" && gameRef.current) {
      setHistory((h) => [{ crash: gameRef.current.crashPoint, win: true }, ...h].slice(0, 14));
    }
  }, [phase]);

  const playing = phase === "playing";
  const crashed = phase === "crashed";
  const cashed = phase === "cashed";
  const color = crashed ? "text-bx-red" : cashed ? "text-bx-green" : playing ? "text-bx-cyan" : "text-white";

  return (
    <div className="space-y-6" data-testid="crash-page">
      <div className="flex items-center gap-3">
        <Rocket className="text-bx-cyan" />
        <h1 className="font-display text-3xl font-black tracking-tight">Crash</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bx-card p-8 min-h-[380px] flex flex-col items-center justify-center relative overflow-hidden">
          <svg className="absolute inset-0 w-full h-full opacity-30" preserveAspectRatio="none" viewBox="0 0 100 100">
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
          {crashed && <div className="relative mt-2 font-display text-xl text-bx-red uppercase tracking-widest">Crashed!</div>}
          {cashed && lastWin && (
            <div className="relative mt-2 font-display text-lg text-bx-green uppercase tracking-widest">
              Cashed +{lastWin.payout.toFixed(2)}
            </div>
          )}
        </div>

        <div className="bx-card p-6 space-y-5">
          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">Bet Amount</label>
            <Input
              type="number" min="1" step="0.01"
              value={amount} onChange={(e) => setAmount(e.target.value)}
              className="bg-[#0B1121] border-[#1E293B] focus-visible:ring-bx-cyan h-11 font-mono"
              disabled={playing}
              data-testid="crash-amount-input"
            />
            <div className="flex gap-2">
              {[0.5, 2, 10].map((m) => (
                <button key={m}
                  onClick={() => setAmount((a) => Math.max(1, Math.round(Number(a) * m * 100) / 100))}
                  disabled={playing}
                  className="text-xs px-3 py-1 rounded bg-[#0B1121] border border-[#1E293B] hover:border-bx-cyan/40 disabled:opacity-50"
                  data-testid={`crash-amount-multiplier-${m}`}
                >{m === 0.5 ? "½" : `${m}x`}</button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">
              Auto Cashout <span className="text-bx-muted/60 normal-case lowercase">(optional)</span>
            </label>
            <Input
              type="number" min="1.01" step="0.01"
              value={autoCashout} onChange={(e) => setAutoCashout(e.target.value)}
              className="bg-[#0B1121] border-[#1E293B] focus-visible:ring-bx-cyan h-11 font-mono"
              disabled={playing}
              placeholder="leave empty for manual"
              data-testid="crash-cashout-input"
            />
          </div>

          {!playing ? (
            <Button
              onClick={place}
              className="w-full h-12 bg-bx-cyan text-[#0B1121] hover:bg-bx-cyan/90 font-display font-bold tracking-wider hover:shadow-[0_0_24px_rgba(0,229,255,0.5)] transition-all"
              data-testid="crash-bet-button"
            >PLACE BET</Button>
          ) : (
            <Button
              onClick={cashoutNow}
              className="w-full h-12 bg-bx-green text-[#0B1121] hover:bg-bx-green/90 font-display font-bold tracking-wider animate-pulse-neon"
              data-testid="crash-cashout-button"
            >CASHOUT @ {displayMult.toFixed(2)}x</Button>
          )}

          <div className="text-xs text-bx-muted text-center">
            Potential: <span className="text-bx-gold font-mono font-bold">{(amount * displayMult).toFixed(2)}</span>
          </div>
        </div>
      </div>

      <div className="bx-card p-4">
        <div className="text-xs uppercase tracking-wider text-bx-muted mb-3 font-bold">Recent Crashes</div>
        <div className="flex gap-2 flex-wrap" data-testid="crash-history">
          {history.length === 0 && <div className="text-xs text-bx-muted">No rounds yet</div>}
          {history.map((h, i) => (
            <div key={i}
              className={`px-3 py-1.5 rounded text-xs font-mono font-bold border ${
                h.crash >= 2 ? "border-bx-green/40 text-bx-green bg-bx-green/5" : "border-bx-red/40 text-bx-red bg-bx-red/5"
              }`}
            >{h.crash.toFixed(2)}x</div>
          ))}
        </div>
      </div>
    </div>
  );
}
