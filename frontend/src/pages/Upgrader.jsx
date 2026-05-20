import React, { useState, useEffect, useRef } from "react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Target } from "lucide-react";
import { toast } from "sonner";

export default function Upgrader() {
  const { refresh } = useAuth();
  const [amount, setAmount] = useState(10);
  const [target, setTarget] = useState(2.0);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [angle, setAngle] = useState(0);
  const [history, setHistory] = useState([]);
  const animRef = useRef(null);

  useEffect(() => () => clearTimeout(animRef.current), []);

  const winProb = Math.min(0.95, 0.95 / target);
  const winArc = winProb * 360;

  const play = async () => {
    if (busy) return;
    setBusy(true); setResult(null); setAngle(0);
    try {
      const { data } = await api.post("/games/upgrader/play", {
        amount: Number(amount), target: Number(target),
      });
      const finalAngle = data.details.angle + 360 * 5; // spin extra rotations
      const start = Date.now(); const dur = 2000;
      const tick = () => {
        const t = Math.min(1, (Date.now() - start) / dur);
        const eased = 1 - Math.pow(1 - t, 3);
        setAngle(finalAngle * eased);
        if (t < 1) {
          animRef.current = setTimeout(tick, 20);
        } else {
          setResult(data);
          setHistory((h) => [{ won: data.result === "win", mult: data.multiplier || target }, ...h].slice(0, 12));
          refresh();
          if (data.result === "win") toast.success(`Upgraded! +${data.payout.toFixed(2)}`);
          else toast.error("Missed");
          setBusy(false);
        }
      };
      tick();
    } catch (e) {
      setBusy(false);
      toast.error(formatApiError(e.response?.data?.detail) || "Play failed");
    }
  };

  // Build conic gradient: green for win arc, slate for lose arc
  const arc = `conic-gradient(from 0deg, #00FF66 0deg ${winArc}deg, #1E293B ${winArc}deg 360deg)`;

  return (
    <div className="space-y-6" data-testid="upgrader-page">
      <div className="flex items-center gap-3">
        <Target className="text-bx-cyan" />
        <h1 className="font-display text-3xl font-black tracking-tight">Upgrader</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bx-card p-8 min-h-[400px] flex flex-col items-center justify-center">
          <div className="relative">
            <div className="w-64 h-64 rounded-full border-4 border-[#1E293B] relative"
                 style={{ background: arc }} data-testid="upgrader-wheel">
              <div className="absolute inset-4 rounded-full bg-[#0B1121] flex items-center justify-center">
                <div className="text-center">
                  <div className="text-[10px] uppercase tracking-widest text-bx-muted">Target</div>
                  <div className="font-display font-black text-3xl text-bx-cyan">{Number(target).toFixed(2)}x</div>
                  <div className="text-xs font-mono text-bx-muted mt-1">{(winProb * 100).toFixed(1)}% chance</div>
                </div>
              </div>
            </div>
            {/* Pointer */}
            <div
              className="absolute top-1/2 left-1/2 origin-bottom"
              style={{
                width: "4px", height: "120px",
                background: "linear-gradient(180deg, #FFD700, transparent)",
                transform: `translate(-50%, -100%) rotate(${angle}deg)`,
                transition: busy ? "none" : "transform 0.3s ease",
              }}
              data-testid="upgrader-pointer"
            />
            <div className="absolute top-1/2 left-1/2 w-3 h-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-bx-gold border-2 border-white" />
          </div>

          {result && (
            <div className={`mt-6 font-display text-xl uppercase tracking-widest ${result.result === "win" ? "text-bx-green" : "text-bx-red"}`}
                 data-testid="upgrader-result">
              {result.result === "win" ? `+${result.payout.toFixed(2)}` : "Missed"}
            </div>
          )}
        </div>

        <div className="bx-card p-6 space-y-5">
          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">Bet</label>
            <Input type="number" min="1" step="0.01" value={amount}
                   onChange={(e) => setAmount(e.target.value)} disabled={busy}
                   className="bg-[#0B1121] border-[#1E293B] focus-visible:ring-bx-cyan h-11 font-mono"
                   data-testid="upgrader-amount-input" />
          </div>

          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">Target Multiplier (1.1 – 50)</label>
            <Input type="number" min="1.1" max="50" step="0.1" value={target}
                   onChange={(e) => setTarget(e.target.value)} disabled={busy}
                   className="bg-[#0B1121] border-[#1E293B] focus-visible:ring-bx-cyan h-11 font-mono"
                   data-testid="upgrader-target-input" />
            <div className="flex gap-1.5">
              {[1.5, 2, 5, 10, 25].map((t) => (
                <button key={t} onClick={() => setTarget(t)} disabled={busy}
                        className="text-xs px-3 py-1 rounded bg-[#0B1121] border border-[#1E293B] hover:border-bx-cyan/40 font-mono disabled:opacity-50"
                        data-testid={`upgrader-preset-${t}`}>{t}x</button>
              ))}
            </div>
          </div>

          <Button onClick={play} disabled={busy}
                  className="w-full h-12 bg-bx-cyan text-[#0B1121] hover:bg-bx-cyan/90 font-display font-bold tracking-wider"
                  data-testid="upgrader-bet-button">
            {busy ? "SPINNING…" : "UPGRADE"}
          </Button>

          <div className="text-xs text-bx-muted text-center">
            Win → <span className="text-bx-gold font-mono font-bold">{(amount * target).toFixed(2)}</span> ({(winProb * 100).toFixed(1)}%)
          </div>

          <div className="flex flex-wrap gap-1.5">
            {history.map((h, i) => (
              <div key={i} className={`w-6 h-6 rounded-full border ${
                h.won ? "bg-bx-green/30 border-bx-green" : "bg-bx-red/30 border-bx-red"
              }`} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
