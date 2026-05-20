import React, { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Spade } from "lucide-react";
import { toast } from "sonner";

function Card({ card, hidden = false }) {
  if (hidden) {
    return (
      <div className="w-16 h-24 rounded-lg bg-bx-purple/20 border-2 border-bx-purple/60 flex items-center justify-center">
        <div className="w-6 h-10 rounded bg-bx-purple/40" />
      </div>
    );
  }
  const rank = card.rank === 1 ? "A" : card.rank === 11 ? "J" : card.rank === 12 ? "Q" : card.rank === 13 ? "K" : card.rank;
  const red = card.suit === "♥" || card.suit === "♦";
  return (
    <div className={`w-16 h-24 rounded-lg bg-white text-black flex flex-col items-center justify-center font-display font-black shadow-lg border-2 border-white/20 ${red ? "text-bx-red" : "text-black"}`}>
      <div className="text-xl leading-none">{rank}</div>
      <div className="text-2xl leading-none">{card.suit}</div>
    </div>
  );
}

export default function Blackjack() {
  const { refresh } = useAuth();
  const [amount, setAmount] = useState(10);
  const [state, setState] = useState(null); // session response
  const [busy, setBusy] = useState(false);

  const start = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/games/blackjack/start", { amount: Number(amount) });
      setState(data);
      refresh();
      if (data.state === "ended") {
        if (data.result === "win") toast.success(`Blackjack! +${data.payout.toFixed(2)}`);
        else if (data.result === "push") toast.info("Push — bet returned");
        else toast.error("Dealer wins");
      }
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Failed");
    } finally { setBusy(false); }
  };

  const action = async (kind) => {
    if (!state || state.state !== "active" || busy) return;
    setBusy(true);
    try {
      const { data } = await api.post(`/games/blackjack/${kind}`, { game_id: state.game_id });
      setState(data);
      refresh();
      if (data.state === "ended") {
        if (data.result === "win") toast.success(`+${data.payout.toFixed(2)}`);
        else if (data.result === "push") toast.info("Push");
        else if (data.result === "bust") toast.error("Bust!");
        else toast.error("Dealer wins");
      }
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Failed");
    } finally { setBusy(false); }
  };

  const newRound = () => setState(null);

  const inGame = state && state.state === "active";
  const ended = state && state.state === "ended";

  return (
    <div className="space-y-6" data-testid="blackjack-page">
      <div className="flex items-center gap-3">
        <Spade className="text-bx-cyan" />
        <h1 className="font-display text-3xl font-black tracking-tight">Blackjack</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bx-card p-8 min-h-[400px] space-y-6">
          {/* Dealer */}
          <div>
            <div className="text-xs uppercase tracking-wider text-bx-muted font-bold mb-3 flex items-center justify-between">
              <span>Dealer</span>
              {state && <span className="font-mono text-white">{state.dealer_total}</span>}
            </div>
            <div className="flex gap-3" data-testid="bj-dealer-cards">
              {state ? (
                inGame ? (
                  <>
                    <Card card={state.dealer_visible[0]} />
                    <Card hidden />
                  </>
                ) : (
                  state.dealer.map((c, i) => <Card key={i} card={c} />)
                )
              ) : (
                <div className="text-sm text-bx-muted italic">Place a bet to start</div>
              )}
            </div>
          </div>

          <div className="h-px bg-[#1E293B]" />

          {/* Player */}
          <div>
            <div className="text-xs uppercase tracking-wider text-bx-muted font-bold mb-3 flex items-center justify-between">
              <span>You</span>
              {state && <span className="font-mono text-bx-cyan font-bold">{state.player_total}</span>}
            </div>
            <div className="flex gap-3" data-testid="bj-player-cards">
              {state && state.player.map((c, i) => <Card key={i} card={c} />)}
            </div>
          </div>

          {ended && (
            <div className={`text-center font-display text-2xl uppercase tracking-widest font-bold ${
              state.result === "win" ? "text-bx-green" :
              state.result === "push" ? "text-bx-cyan" : "text-bx-red"
            }`} data-testid="bj-result">
              {state.result === "win" ? `WIN +${state.payout.toFixed(2)}` :
               state.result === "push" ? "PUSH" :
               state.result === "bust" ? "BUST" : "DEALER WINS"}
            </div>
          )}
        </div>

        <div className="bx-card p-6 space-y-5">
          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">Bet</label>
            <Input type="number" min="1" step="0.01" value={amount}
                   onChange={(e) => setAmount(e.target.value)} disabled={inGame || busy}
                   className="bg-[#0B1121] border-[#1E293B] focus-visible:ring-bx-cyan h-11 font-mono"
                   data-testid="bj-amount-input" />
          </div>

          {!state || ended ? (
            <Button onClick={ended ? newRound : start} disabled={busy}
                    className="w-full h-12 bg-bx-cyan text-[#0B1121] hover:bg-bx-cyan/90 font-display font-bold tracking-wider"
                    data-testid="bj-deal-button">
              {ended ? "NEW ROUND" : busy ? "DEALING…" : "DEAL"}
            </Button>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <Button onClick={() => action("hit")} disabled={busy}
                      className="h-12 bg-bx-green text-[#0B1121] hover:bg-bx-green/90 font-display font-bold tracking-wider"
                      data-testid="bj-hit-button">HIT</Button>
              <Button onClick={() => action("stand")} disabled={busy}
                      className="h-12 bg-bx-red text-white hover:bg-bx-red/90 font-display font-bold tracking-wider"
                      data-testid="bj-stand-button">STAND</Button>
            </div>
          )}

          <div className="text-xs text-bx-muted text-center">
            Blackjack pays <span className="text-bx-gold font-mono font-bold">3:2</span>
          </div>
        </div>
      </div>
    </div>
  );
}
