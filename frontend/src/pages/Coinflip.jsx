import React, { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Coins } from "lucide-react";
import { toast } from "sonner";

export default function Coinflip() {
  const { refresh } = useAuth();
  const [amount, setAmount] = useState(10);
  const [side, setSide] = useState("heads");
  const [playing, setPlaying] = useState(false);
  const [result, setResult] = useState(null);
  const [flipping, setFlipping] = useState(false);

  const play = async () => {
    setPlaying(true);
    setResult(null);
    setFlipping(true);
    try {
      const { data } = await api.post("/games/coinflip/play", {
        amount: Number(amount), side,
      });
      // Animate
      setTimeout(() => {
        setFlipping(false);
        setResult(data);
        refresh();
        if (data.result === "win") toast.success(`Won ${data.payout.toFixed(2)}!`);
        else toast.error(`Lost — landed on ${data.details.flip}`);
      }, 1400);
    } catch (e) {
      setFlipping(false);
      toast.error(formatApiError(e.response?.data?.detail) || "Bet failed");
    } finally {
      setPlaying(false);
    }
  };

  const coinFace = flipping ? "flipping" : result?.details.flip || side;

  return (
    <div className="space-y-6" data-testid="coinflip-page">
      <div className="flex items-center gap-3">
        <Coins className="text-bx-gold" />
        <h1 className="font-display text-3xl font-black tracking-tight">Coinflip</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bx-card p-8 min-h-[360px] flex flex-col items-center justify-center">
          <div
            className={`w-40 h-40 rounded-full flex items-center justify-center font-display text-4xl font-black border-4 transition-all duration-300 ${
              flipping ? "animate-spin-slow border-bx-cyan bx-glow" :
              coinFace === "heads" ? "border-bx-gold bg-gradient-to-br from-bx-gold/30 to-bx-gold/5 text-bx-gold bx-glow" :
              "border-bx-purple bg-gradient-to-br from-bx-purple/30 to-bx-purple/5 text-bx-purple bx-glow-purple"
            }`}
            data-testid="coinflip-coin"
          >
            {flipping ? "?" : coinFace === "heads" ? "H" : "T"}
          </div>
          {result && (
            <div className={`mt-6 font-display text-xl uppercase tracking-widest ${result.result === "win" ? "text-bx-green" : "text-bx-red"}`} data-testid="coinflip-result">
              {result.result === "win" ? `+${result.payout.toFixed(2)}` : "You Lost"}
            </div>
          )}
        </div>

        <div className="bx-card p-6 space-y-5">
          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">Bet Amount</label>
            <Input
              type="number" min="1" step="0.01" value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="bg-[#0B1121] border-[#1E293B] focus-visible:ring-bx-cyan h-11 font-mono"
              disabled={playing}
              data-testid="coinflip-amount-input"
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">Pick Side</label>
            <div className="grid grid-cols-2 gap-2">
              {["heads", "tails"].map((s) => (
                <button
                  key={s}
                  onClick={() => setSide(s)}
                  disabled={playing}
                  className={`h-11 rounded-lg font-display font-bold uppercase text-sm tracking-wider transition-all border-2 ${
                    side === s
                      ? s === "heads"
                        ? "border-bx-gold bg-bx-gold/10 text-bx-gold"
                        : "border-bx-purple bg-bx-purple/10 text-bx-purple"
                      : "border-[#1E293B] text-bx-muted hover:border-bx-muted"
                  }`}
                  data-testid={`coinflip-side-${s}`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          <Button
            onClick={play}
            disabled={playing}
            className="w-full h-12 bg-bx-cyan text-[#0B1121] hover:bg-bx-cyan/90 font-display font-bold tracking-wider hover:shadow-[0_0_24px_rgba(0,229,255,0.5)] transition-all"
            data-testid="coinflip-bet-button"
          >
            {playing ? "FLIPPING…" : "FLIP COIN"}
          </Button>

          <div className="text-xs text-bx-muted text-center">
            Payout: <span className="text-bx-gold font-mono font-bold">1.95x</span> · Win: <span className="text-bx-green font-mono">+{(amount * 0.95).toFixed(2)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
