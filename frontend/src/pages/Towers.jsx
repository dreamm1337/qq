import React, { useState, useRef, useEffect } from "react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Building2, Bomb, Gem } from "lucide-react";
import { toast } from "sonner";

const DIFFS = {
  easy:   { cols: 4, label: "Easy",   safe: 3 },
  medium: { cols: 3, label: "Medium", safe: 2 },
  hard:   { cols: 2, label: "Hard",   safe: 1 },
};

export default function Towers() {
  const { refresh } = useAuth();
  const [amount, setAmount] = useState(10);
  const [difficulty, setDifficulty] = useState("medium");
  const [gameId, setGameId] = useState(null);
  const [cfg, setCfg] = useState({ rows: 8, cols: 3 });
  const [path, setPath] = useState([]); // chosen cols by row
  const [revealed, setRevealed] = useState({}); // {`row-col`: 'gem'|'bomb'|'bomb-shown'}
  const [multiplier, setMultiplier] = useState(0);
  const [nextMultiplier, setNextMultiplier] = useState(0);
  const [busy, setBusy] = useState(false);
  const clearTimerRef = useRef(null);

  useEffect(() => () => clearTimeout(clearTimerRef.current), []);

  const inGame = !!gameId;
  const currentRow = path.length;

  const start = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/games/towers/start", {
        amount: Number(amount), difficulty,
      });
      setGameId(data.game_id);
      setCfg({ rows: data.rows, cols: data.cols });
      setPath([]); setRevealed({}); setMultiplier(0); setNextMultiplier(0);
      refresh();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Failed");
    } finally { setBusy(false); }
  };

  const pick = async (col) => {
    if (!inGame || busy) return;
    setBusy(true);
    try {
      const { data } = await api.post("/games/towers/pick", { game_id: gameId, col });
      if (data.status === "busted") {
        const map = { ...revealed };
        data.bombs.forEach((bcol, r) => {
          if (r <= currentRow) {
            map[`${r}-${bcol}`] = r === currentRow ? "bomb" : "bomb-shown";
          }
        });
        setRevealed(map);
        toast.error("Boom! Hit a bomb");
        endGame();
      } else if (data.status === "safe") {
        setRevealed((r) => ({ ...r, [`${currentRow}-${col}`]: "gem" }));
        setPath(data.path);
        setMultiplier(data.multiplier);
        setNextMultiplier(data.next_multiplier);
      } else if (data.status === "completed") {
        setRevealed((r) => ({ ...r, [`${currentRow}-${col}`]: "gem" }));
        setPath(data.path);
        setMultiplier(data.multiplier);
        toast.success(`Completed! +${data.bet.payout.toFixed(2)}`);
        endGame();
      }
      refresh();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Pick failed");
    } finally { setBusy(false); }
  };

  const cashout = async () => {
    if (!inGame || busy || path.length === 0) return;
    setBusy(true);
    try {
      const { data } = await api.post("/games/towers/cashout", { game_id: gameId });
      if (data.status === "cashed") {
        toast.success(`Cashed +${data.payout.toFixed(2)} @ ${data.multiplier.toFixed(2)}x`);
        setMultiplier(data.multiplier);
      }
      endGame();
      refresh();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Cashout failed");
    } finally { setBusy(false); }
  };

  const endGame = () => {
    setGameId(null);
    clearTimeout(clearTimerRef.current);
    clearTimerRef.current = setTimeout(() => {
      setPath([]); setRevealed({}); setMultiplier(0); setNextMultiplier(0);
    }, 2200);
  };

  // Render rows bottom-up so player climbs up
  const rows = Array.from({ length: cfg.rows }, (_, i) => cfg.rows - 1 - i);

  return (
    <div className="space-y-6" data-testid="towers-page">
      <div className="flex items-center gap-3">
        <Building2 className="text-bx-cyan" />
        <h1 className="font-display text-3xl font-black tracking-tight">Towers</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bx-card p-6">
          <div className="space-y-1.5 max-w-md mx-auto">
            {rows.map((row) => {
              const isActive = inGame && row === currentRow;
              return (
                <div key={row} className={`grid gap-2 ${isActive ? "" : "opacity-70"}`}
                     style={{ gridTemplateColumns: `repeat(${cfg.cols}, minmax(0, 1fr))` }}
                     data-testid={`towers-row-${row}`}>
                  {Array.from({ length: cfg.cols }, (_, c) => {
                    const key = `${row}-${c}`;
                    const rev = revealed[key];
                    const isOnPath = path[row] === c;
                    const base = "h-12 rounded-lg flex items-center justify-center border-2 transition-all";
                    let cls = `${base} bg-[#0B1121] border-[#1E293B]`;
                    if (isActive) cls += " hover:border-bx-cyan/60 cursor-pointer";
                    else cls += " cursor-default";
                    if (rev === "gem" || isOnPath) cls = `${base} bg-bx-green/15 border-bx-green/60`;
                    if (rev === "bomb") cls = `${base} bg-bx-red/20 border-bx-red animate-pulse-neon`;
                    if (rev === "bomb-shown") cls = `${base} bg-bx-red/5 border-bx-red/30 opacity-60`;
                    return (
                      <button key={c} onClick={() => isActive && pick(c)}
                              disabled={!isActive || busy} className={cls}
                              data-testid={`towers-cell-${row}-${c}`}>
                        {rev === "gem" || isOnPath ? <Gem size={18} className="text-bx-green" /> : null}
                        {(rev === "bomb" || rev === "bomb-shown") && <Bomb size={18} className="text-bx-red" />}
                      </button>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>

        <div className="bx-card p-6 space-y-5">
          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">Bet</label>
            <Input type="number" min="1" step="0.01" value={amount}
                   onChange={(e) => setAmount(e.target.value)}
                   className="bg-[#0B1121] border-[#1E293B] focus-visible:ring-bx-cyan h-11 font-mono"
                   disabled={inGame} data-testid="towers-amount-input" />
          </div>

          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">Difficulty</label>
            <div className="grid grid-cols-3 gap-2">
              {Object.entries(DIFFS).map(([k, v]) => (
                <button key={k} onClick={() => setDifficulty(k)} disabled={inGame}
                        className={`h-10 rounded-lg font-display text-xs uppercase tracking-wider font-bold border-2 transition ${
                          difficulty === k ? "border-bx-cyan bg-bx-cyan/10 text-bx-cyan" : "border-[#1E293B] text-bx-muted hover:border-bx-muted"
                        }`}
                        data-testid={`towers-diff-${k}`}>
                  {v.label}
                </button>
              ))}
            </div>
          </div>

          {inGame && (
            <div className="bx-card p-3 bg-[#0B1121] text-center space-y-1">
              <div className="text-[10px] uppercase tracking-widest text-bx-muted">Current</div>
              <div className="font-mono font-bold text-2xl text-bx-green">{multiplier.toFixed(2)}x</div>
              <div className="text-xs text-bx-muted">Next: <span className="text-bx-cyan font-mono">{nextMultiplier ? nextMultiplier.toFixed(2) + "x" : "—"}</span></div>
            </div>
          )}

          {!inGame ? (
            <Button onClick={start} disabled={busy}
                    className="w-full h-12 bg-bx-cyan text-[#0B1121] hover:bg-bx-cyan/90 font-display font-bold tracking-wider"
                    data-testid="towers-start-button">
              {busy ? "STARTING…" : "PLACE BET"}
            </Button>
          ) : (
            <Button onClick={cashout} disabled={busy || path.length === 0}
                    className="w-full h-12 bg-bx-green text-[#0B1121] hover:bg-bx-green/90 font-display font-bold tracking-wider disabled:opacity-40"
                    data-testid="towers-cashout-button">
              CASHOUT {multiplier > 0 ? `+${(amount * multiplier - amount).toFixed(2)}` : ""}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
