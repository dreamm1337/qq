import React, { useState, useRef, useEffect } from "react";
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
  const [gameId, setGameId] = useState(null);
  const [revealed, setRevealed] = useState({}); // {idx: 'gem'|'bomb'|'bomb-shown'}
  const [multiplier, setMultiplier] = useState(0.0);
  const [nextMultiplier, setNextMultiplier] = useState(0.0);
  const [busy, setBusy] = useState(false);
  const [pendingTile, setPendingTile] = useState(null);
  const clearTimerRef = useRef(null);

  useEffect(() => () => clearTimeout(clearTimerRef.current), []);

  const inGame = !!gameId;

  const startGame = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const { data } = await api.post("/games/mines/start", {
        amount: Number(amount), mines: Number(mines),
      });
      setGameId(data.game_id);
      setRevealed({});
      setMultiplier(0);
      setNextMultiplier(0);
      refresh();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Failed to start");
    } finally {
      setBusy(false);
    }
  };

  const revealTile = async (idx) => {
    if (!inGame || busy || revealed[idx] !== undefined) return;
    setBusy(true);
    setPendingTile(idx);
    try {
      const { data } = await api.post("/games/mines/reveal", { game_id: gameId, tile: idx });
      if (data.status === "busted") {
        // mark all bombs, show clicked one as bomb
        const map = {};
        data.bombs.forEach((b) => { map[b] = b === idx ? "bomb" : "bomb-shown"; });
        // mark previously revealed as gem
        Object.entries(revealed).forEach(([k, v]) => { if (v === "gem") map[k] = "gem"; });
        setRevealed(map);
        setMultiplier(0);
        toast.error("Boom! You hit a mine");
        endGame();
      } else if (data.status === "safe") {
        setRevealed((r) => ({ ...r, [idx]: "gem" }));
        setMultiplier(data.multiplier);
        setNextMultiplier(data.next_multiplier);
      } else if (data.status === "cleared") {
        setRevealed((r) => ({ ...r, [idx]: "gem" }));
        setMultiplier(data.multiplier);
        toast.success(`Cleared! +${data.bet.payout.toFixed(2)} @ ${data.multiplier.toFixed(2)}x`);
        endGame();
      }
      refresh();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Reveal failed");
    } finally {
      setBusy(false);
      setPendingTile(null);
    }
  };

  const cashout = async () => {
    if (!inGame || busy) return;
    if (Object.values(revealed).filter((v) => v === "gem").length === 0) {
      toast.error("Reveal at least one tile first");
      return;
    }
    setBusy(true);
    try {
      const { data } = await api.post("/games/mines/cashout", { game_id: gameId });
      if (data.status === "cashed") {
        // Show all bombs as faded
        const map = { ...revealed };
        data.bombs.forEach((b) => { if (map[b] === undefined) map[b] = "bomb-shown"; });
        setRevealed(map);
        setMultiplier(data.multiplier);
        toast.success(`Cashed +${data.payout.toFixed(2)} @ ${data.multiplier.toFixed(2)}x`);
      }
      endGame();
      refresh();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Cashout failed");
    } finally {
      setBusy(false);
    }
  };

  // After game ends, auto-clear board after a brief delay
  const endGame = () => {
    setGameId(null);
    clearTimeout(clearTimerRef.current);
    clearTimerRef.current = setTimeout(() => {
      setRevealed({});
      setMultiplier(0);
      setNextMultiplier(0);
    }, 2200);
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
              const rev = revealed[i];
              const isPending = pendingTile === i;
              const base = "aspect-square rounded-lg flex items-center justify-center transition-all duration-200 border-2";
              let cls = `${base} bg-[#0B1121] border-[#1E293B] ${inGame ? "hover:border-bx-cyan/50 cursor-pointer" : "cursor-not-allowed opacity-60"}`;
              if (rev === "gem") cls = `${base} bg-bx-green/15 border-bx-green/60 cursor-default`;
              if (rev === "bomb") cls = `${base} bg-bx-red/20 border-bx-red animate-pulse-neon cursor-default`;
              if (rev === "bomb-shown") cls = `${base} bg-bx-red/5 border-bx-red/30 opacity-50 cursor-default`;
              if (isPending) cls += " animate-pulse";
              return (
                <button
                  key={i}
                  onClick={() => revealTile(i)}
                  disabled={!inGame || busy || rev !== undefined}
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
              disabled={inGame}
              data-testid="mines-amount-input"
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">Mines (1-24)</label>
            <Input
              type="number" min="1" max="24" value={mines}
              onChange={(e) => setMines(e.target.value)}
              className="bg-[#0B1121] border-[#1E293B] focus-visible:ring-bx-cyan h-11 font-mono"
              disabled={inGame}
              data-testid="mines-count-input"
            />
          </div>

          {inGame && (
            <div className="bx-card p-3 bg-[#0B1121] text-center space-y-1">
              <div className="text-[10px] uppercase tracking-widest text-bx-muted">Current</div>
              <div className="font-mono font-bold text-2xl text-bx-green" data-testid="mines-current-multiplier">
                {multiplier.toFixed(2)}x
              </div>
              <div className="text-xs text-bx-muted">
                Next: <span className="text-bx-cyan font-mono">{nextMultiplier ? nextMultiplier.toFixed(2) + "x" : "—"}</span>
              </div>
            </div>
          )}

          {!inGame ? (
            <Button
              onClick={startGame}
              disabled={busy}
              className="w-full h-12 bg-bx-cyan text-[#0B1121] hover:bg-bx-cyan/90 font-display font-bold tracking-wider hover:shadow-[0_0_24px_rgba(0,229,255,0.5)] transition-all"
              data-testid="mines-bet-button"
            >{busy ? "STARTING…" : "PLACE BET"}</Button>
          ) : (
            <Button
              onClick={cashout}
              disabled={busy || Object.values(revealed).filter((v) => v === "gem").length === 0}
              className="w-full h-12 bg-bx-green text-[#0B1121] hover:bg-bx-green/90 font-display font-bold tracking-wider disabled:opacity-40"
              data-testid="mines-cashout-button"
            >CASHOUT {multiplier > 0 ? `+${(amount * multiplier - amount).toFixed(2)}` : ""}</Button>
          )}
        </div>
      </div>
    </div>
  );
}
