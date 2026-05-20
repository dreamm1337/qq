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

// SVG board geometry
const BOARD_W = 480;
const BOARD_H = 440;
const PEG_DX = 38;
const PEG_DY = 36;
const PEG_TOP = 30;
const CENTER_X = BOARD_W / 2;
const SLOT_Y = PEG_TOP + ROWS * PEG_DY + 30;

const pegPos = (row, col) => ({
  x: CENTER_X - row * (PEG_DX / 2) + col * PEG_DX,
  y: PEG_TOP + row * PEG_DY,
});
const slotX = (i) => CENTER_X - ROWS * (PEG_DX / 2) + i * PEG_DX;

export default function Plinko() {
  const { refresh } = useAuth();
  const [amount, setAmount] = useState(10);
  const [risk, setRisk] = useState("medium");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [ball, setBall] = useState(null); // {x, y, finalSlot}
  const rafRef = useRef(null);

  useEffect(() => () => cancelAnimationFrame(rafRef.current), []);

  const play = async () => {
    if (busy) return;
    setBusy(true);
    setResult(null);
    setBall(null);
    try {
      const { data } = await api.post("/games/plinko/play", {
        amount: Number(amount), risk,
      });
      const path = data.details.path; // [0/1, ...] length 8 (right moves)

      // Compute keyframe positions: start above peg(0,0), then through each row's landing position
      const frames = [];
      const first = pegPos(0, 0);
      frames.push({ x: first.x, y: first.y - 16 });
      frames.push({ x: first.x, y: first.y }); // touch first peg
      let col = 0;
      for (let r = 0; r < ROWS; r++) {
        if (path[r] === 1) col += 1;
        const p = pegPos(r + 1, col);
        frames.push({ x: p.x, y: p.y });
      }
      const finalSlot = data.details.slot;
      frames.push({ x: slotX(finalSlot), y: SLOT_Y - 12 });

      const dur = 1700; // total ms
      const start = performance.now();
      const animate = (now) => {
        const t = Math.min(1, (now - start) / dur);
        // Map t to segment i in (0..frames.length-1)
        const totalSeg = frames.length - 1;
        const segPos = t * totalSeg;
        const i = Math.min(Math.floor(segPos), totalSeg - 1);
        const local = segPos - i;
        // Ease each segment a bit
        const e = local * local * (3 - 2 * local);
        const a = frames[i];
        const b = frames[i + 1] || frames[i];
        if (!a || !b) {
          setBusy(false);
          return;
        }
        // Add slight arc on Y for bounce feel
        const arc = Math.sin(local * Math.PI) * 4;
        setBall({ x: a.x + (b.x - a.x) * e, y: a.y + (b.y - a.y) * e - arc, finalSlot });
        if (t < 1) {
          rafRef.current = requestAnimationFrame(animate);
        } else {
          setResult(data);
          setHistory((h) => [{ slot: data.details.slot, mult: data.multiplier }, ...h].slice(0, 12));
          refresh();
          if (data.result === "win") toast.success(`+${data.payout.toFixed(2)} @ ${data.multiplier}x`);
          else toast.error(`Landed ${data.multiplier}x — lost`);
          setBusy(false);
        }
      };
      rafRef.current = requestAnimationFrame(animate);
    } catch (e) {
      setBusy(false);
      toast.error(formatApiError(e.response?.data?.detail) || "Play failed");
    }
  };

  const table = TABLES[risk];

  return (
    <div className="space-y-6" data-testid="plinko-page">
      <div className="flex items-center gap-3">
        <Circle className="text-bx-cyan" />
        <h1 className="font-display text-3xl font-black tracking-tight">Plinko</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bx-card p-6 flex items-center justify-center">
          <div className="relative w-full max-w-[520px]">
          <svg
            viewBox={`0 0 ${BOARD_W} ${BOARD_H}`}
            className="w-full h-auto"
            data-testid="plinko-board"
            style={{ filter: "drop-shadow(0 0 24px rgba(0,229,255,0.15))" }}
          >
            <defs>
              <radialGradient id="ballGrad" cx="35%" cy="35%">
                <stop offset="0%" stopColor="#FFFFFF" />
                <stop offset="40%" stopColor="#FFD700" />
                <stop offset="100%" stopColor="#B8860B" />
              </radialGradient>
              <filter id="ballGlow">
                <feGaussianBlur stdDeviation="3" result="b" />
                <feMerge>
                  <feMergeNode in="b" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            {/* Pegs */}
            {Array.from({ length: ROWS + 1 }, (_, r) =>
              Array.from({ length: r + 1 }, (_, c) => {
                const p = pegPos(r, c);
                return (
                  <circle
                    key={`${r}-${c}`}
                    cx={p.x} cy={p.y} r={3.2}
                    fill="#00E5FF"
                    opacity={0.7}
                  />
                );
              })
            )}

            {/* Slots */}
            {table.map((mult, i) => {
              const x = slotX(i) - PEG_DX / 2 + 3;
              const w = PEG_DX - 6;
              const landed = result && result.details.slot === i;
              const tone =
                mult >= 5 ? { fill: "rgba(255,215,0,0.16)", stroke: "#FFD700", text: "#FFD700" } :
                mult >= 1 ? { fill: "rgba(0,255,102,0.12)", stroke: "rgba(0,255,102,0.5)", text: "#00FF66" } :
                            { fill: "rgba(255,0,85,0.12)", stroke: "rgba(255,0,85,0.5)", text: "#FF0055" };
              return (
                <g key={i} data-testid={`plinko-slot-${i}`}>
                  <rect
                    x={x} y={SLOT_Y - 8} width={w} height={32} rx={6}
                    fill={tone.fill} stroke={tone.stroke} strokeWidth={landed ? 2.5 : 1}
                    style={landed ? { filter: `drop-shadow(0 0 10px ${tone.stroke})` } : {}}
                  />
                  <text
                    x={x + w / 2} y={SLOT_Y + 13}
                    textAnchor="middle"
                    fontFamily="JetBrains Mono, monospace"
                    fontWeight="800"
                    fontSize="13"
                    fill={tone.text}
                  >
                    {mult}x
                  </text>
                </g>
              );
            })}

            {/* Ball */}
            {ball && (
              <circle
                cx={ball.x} cy={ball.y} r={7}
                fill="url(#ballGrad)"
                filter="url(#ballGlow)"
              />
            )}
          </svg>

          {/* HTML slot labels overlay (crisper text than SVG at scale) */}
          <div className="absolute inset-0 pointer-events-none">
            {table.map((mult, i) => {
              const landed = result && result.details.slot === i;
              const tone =
                mult >= 5 ? "text-bx-gold" :
                mult >= 1 ? "text-bx-green" : "text-bx-red";
              const leftPct = ((slotX(i) - PEG_DX / 2 + 3) / BOARD_W) * 100;
              const widthPct = ((PEG_DX - 6) / BOARD_W) * 100;
              const topPct = ((SLOT_Y - 6) / BOARD_H) * 100;
              return (
                <div
                  key={i}
                  className={`absolute flex items-center justify-center font-mono font-extrabold text-xs sm:text-sm ${tone} ${landed ? "scale-110" : ""}`}
                  style={{
                    left: `${leftPct}%`,
                    top: `${topPct}%`,
                    width: `${widthPct}%`,
                    height: `7.5%`,
                  }}
                >
                  {mult}x
                </div>
              );
            })}
          </div>
          </div>
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

          {result && (
            <div className={`text-center font-display text-sm font-bold ${result.result === "win" ? "text-bx-green" : "text-bx-red"}`}
                 data-testid="plinko-result">
              Slot {result.details.slot} · {result.multiplier}x {result.result === "win" ? `· +${result.payout.toFixed(2)}` : ""}
            </div>
          )}

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
