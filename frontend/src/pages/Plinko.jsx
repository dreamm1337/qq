import React, { useState, useEffect, useRef } from "react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Circle } from "lucide-react";
import { toast } from "sonner";

const ROWS = 8;
const TABLES = {
  low:    [5.6, 2.1, 1.1, 1.0, 0.5, 1.0, 1.1, 2.1, 5.6],
  medium: [13, 3, 1.3, 0.7, 0.4, 0.7, 1.3, 3, 13],
  high:   [29, 4, 1.5, 0.3, 0.2, 0.3, 1.5, 4, 29],
};

export default function Plinko() {
  const { refresh } = useAuth();
  const [amount, setAmount] = useState(10);
  const [risk, setRisk] = useState("medium");
  const [busy, setBusy] = useState(false);
  const [ballRow, setBallRow] = useState(-1); // current ball row during anim
  const [ballPath, setBallPath] = useState([]); // cumulative right offsets per row (0..row)
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const animRef = useRef(null);

  useEffect(() => () => clearTimeout(animRef.current), []);

  const play = async () => {
    if (busy) return;
    setBusy(true);
    setBallRow(-1); setResult(null); setBallPath([]);
    try {
      const { data } = await api.post("/games/plinko/play", {
        amount: Number(amount), risk,
      });
      const path = data.details.path; // [0,1,0,1,...] length 8
      // Animate row by row
      let offset = 0;
      const offsets = [0];
      path.forEach((p) => {
        offset += p;
        offsets.push(offset);
      });
      const step = (i) => {
        setBallRow(i);
        setBallPath(offsets.slice(0, i + 1));
        if (i < ROWS) {
          animRef.current = setTimeout(() => step(i + 1), 220);
        } else {
          setResult(data);
          setHistory((h) => [{ slot: data.details.slot, mult: data.multiplier }, ...h].slice(0, 12));
          refresh();
          if (data.result === "win") toast.success(`+${data.payout.toFixed(2)} @ ${data.multiplier}x`);
          else toast.error(`Landed ${data.multiplier}x — lost`);
          setBusy(false);
        }
      };
      step(0);
    } catch (e) {
      setBusy(false);
      toast.error(formatApiError(e.response?.data?.detail) || "Play failed");
    }
  };

  const table = TABLES[risk];
  const slots = ROWS + 1;
  const ballOffset = ballPath.length > 0 ? ballPath[ballPath.length - 1] : null;

  return (
    <div className="space-y-6" data-testid="plinko-page">
      <div className="flex items-center gap-3">
        <Circle className="text-bx-cyan" />
        <h1 className="font-display text-3xl font-black tracking-tight">Plinko</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bx-card p-6">
          <div className="relative max-w-md mx-auto py-4" data-testid="plinko-board">
            {/* Pegs */}
            {Array.from({ length: ROWS + 1 }, (_, r) => (
              <div key={r} className="relative flex justify-center mb-2"
                   style={{ marginLeft: `${-r * 8}px`, marginRight: `${-r * 8}px` }}>
                <div className="flex gap-3">
                  {Array.from({ length: r + 1 }, (_, c) => {
                    const isBallHere = ballRow === r && ballPath[r] === c;
                    return (
                      <div key={c} className="relative">
                        <div className="w-2 h-2 rounded-full bg-bx-cyan/40" />
                        {isBallHere && (
                          <div className="absolute -top-3 left-1/2 -translate-x-1/2 w-4 h-4 rounded-full bg-bx-gold border-2 border-white shadow-[0_0_12px_rgba(255,215,0,0.7)]" />
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}

            {/* Slots */}
            <div className="flex justify-center gap-1.5 mt-3"
                 style={{ marginLeft: `${-(ROWS) * 4}px`, marginRight: `${-(ROWS) * 4}px` }}>
              {table.map((mult, i) => {
                const landed = result && result.details.slot === i;
                const tone = mult >= 5 ? "text-bx-gold border-bx-gold/60 bg-bx-gold/10" :
                             mult >= 1 ? "text-bx-green border-bx-green/40 bg-bx-green/10" :
                                          "text-bx-red border-bx-red/40 bg-bx-red/10";
                return (
                  <div key={i} className={`flex-1 text-center py-1.5 rounded text-[10px] font-mono font-bold border ${tone} ${landed ? "animate-pulse-neon bx-glow" : ""}`}
                       data-testid={`plinko-slot-${i}`}>
                    {mult}x
                  </div>
                );
              })}
            </div>
          </div>

          {result && (
            <div className={`mt-4 text-center font-display text-lg ${result.result === "win" ? "text-bx-green" : "text-bx-red"}`}
                 data-testid="plinko-result">
              Slot {result.details.slot} · {result.multiplier}x · {result.result === "win" ? `+${result.payout.toFixed(2)}` : "lost"}
            </div>
          )}
        </div>

        <div className="bx-card p-6 space-y-5">
          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">Bet</label>
            <Input type="number" min="1" step="0.01" value={amount}
                   onChange={(e) => setAmount(e.target.value)} disabled={busy}
                   className="bg-[#0B1121] border-[#1E293B] focus-visible:ring-bx-cyan h-11 font-mono"
                   data-testid="plinko-amount-input" />
          </div>

          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">Risk</label>
            <div className="grid grid-cols-3 gap-2">
              {Object.keys(TABLES).map((k) => (
                <button key={k} onClick={() => setRisk(k)} disabled={busy}
                        className={`h-10 rounded-lg font-display text-xs uppercase tracking-wider font-bold border-2 transition ${
                          risk === k ? "border-bx-cyan bg-bx-cyan/10 text-bx-cyan" : "border-[#1E293B] text-bx-muted hover:border-bx-muted"
                        }`}
                        data-testid={`plinko-risk-${k}`}>{k}</button>
              ))}
            </div>
          </div>

          <Button onClick={play} disabled={busy}
                  className="w-full h-12 bg-bx-cyan text-[#0B1121] hover:bg-bx-cyan/90 font-display font-bold tracking-wider"
                  data-testid="plinko-bet-button">
            {busy ? "DROPPING…" : "DROP BALL"}
          </Button>

          <div className="space-y-2">
            <div className="text-[10px] uppercase tracking-widest text-bx-muted">Recent</div>
            <div className="flex flex-wrap gap-1.5">
              {history.length === 0 && <div className="text-xs text-bx-muted">No drops yet</div>}
              {history.map((h, i) => (
                <div key={i} className={`px-2 py-1 rounded text-xs font-mono font-bold border ${
                  h.mult >= 1 ? "border-bx-green/40 text-bx-green" : "border-bx-red/40 text-bx-red"
                }`}>{h.mult}x</div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
