import React, { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { CircleDot } from "lucide-react";
import { toast } from "sonner";

const CHOICES = [
  { id: "red", label: "Red", mult: "2x", text: "text-bx-red", bg: "bg-bx-red/10", border: "border-bx-red/60" },
  { id: "green", label: "Green", mult: "14x", text: "text-bx-green", bg: "bg-bx-green/10", border: "border-bx-green/60" },
  { id: "black", label: "Black", mult: "2x", text: "text-white", bg: "bg-[#0B1121]", border: "border-bx-muted/60" },
];

export default function Roulette() {
  const { refresh } = useAuth();
  const [amount, setAmount] = useState(10);
  const [choice, setChoice] = useState("red");
  const [playing, setPlaying] = useState(false);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [spinning, setSpinning] = useState(false);

  const play = async () => {
    setPlaying(true);
    setResult(null);
    setSpinning(true);
    try {
      const { data } = await api.post("/games/roulette/play", {
        amount: Number(amount), choice,
      });
      setTimeout(() => {
        setSpinning(false);
        setResult(data);
        setHistory((h) => [data.details.result, ...h].slice(0, 15));
        refresh();
        if (data.result === "win") toast.success(`Won ${data.payout.toFixed(2)}!`);
        else toast.error(`Lost — landed on ${data.details.result}`);
      }, 1600);
    } catch (e) {
      setSpinning(false);
      toast.error(formatApiError(e.response?.data?.detail) || "Bet failed");
    } finally {
      setPlaying(false);
    }
  };

  const landed = spinning ? null : result?.details.result;

  const landedStyle =
    landed === "red" ? "bg-bx-red/20 border-bx-red text-bx-red" :
    landed === "green" ? "bg-bx-green/20 border-bx-green text-bx-green" :
    landed === "black" ? "bg-[#0B1121] border-white text-white" :
    "bg-[#131A2A] border-[#1E293B] text-bx-muted";

  return (
    <div className="space-y-6" data-testid="roulette-page">
      <div className="flex items-center gap-3">
        <CircleDot className="text-bx-red" />
        <h1 className="font-display text-3xl font-black tracking-tight">Roulette</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bx-card p-8 min-h-[300px] flex flex-col items-center justify-center">
          <div
            className={`w-48 h-48 rounded-full flex items-center justify-center font-display font-black text-4xl uppercase border-4 transition-all ${landedStyle} ${spinning ? "animate-spin-slow border-bx-cyan" : ""}`}
            data-testid="roulette-wheel"
          >
            {spinning ? "•••" : landed || "?"}
          </div>

          {result && !spinning && (
            <div className={`mt-5 font-display text-xl uppercase tracking-widest ${result.result === "win" ? "text-bx-green" : "text-bx-red"}`} data-testid="roulette-result">
              {result.result === "win" ? `+${result.payout.toFixed(2)}` : "You Lost"}
            </div>
          )}

          <div className="mt-6 flex gap-1.5 flex-wrap justify-center" data-testid="roulette-history">
            {history.map((c, i) => (
              <div
                key={i}
                className={`w-6 h-6 rounded-full border ${
                  c === "red" ? "bg-bx-red border-bx-red" :
                  c === "green" ? "bg-bx-green border-bx-green" :
                  "bg-[#0B1121] border-bx-muted"
                }`}
              />
            ))}
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
              data-testid="roulette-amount-input"
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">Pick Color</label>
            <div className="space-y-2">
              {CHOICES.map((c) => (
                <button
                  key={c.id}
                  onClick={() => setChoice(c.id)}
                  disabled={playing}
                  className={`w-full h-11 px-4 rounded-lg font-display font-bold uppercase text-sm tracking-wider transition-all border-2 flex items-center justify-between ${
                    choice === c.id ? `${c.bg} ${c.border} ${c.text}` : "border-[#1E293B] text-bx-muted hover:border-bx-muted"
                  }`}
                  data-testid={`roulette-choice-${c.id}`}
                >
                  <span>{c.label}</span>
                  <span className="font-mono text-xs">{c.mult}</span>
                </button>
              ))}
            </div>
          </div>

          <Button
            onClick={play}
            disabled={playing}
            className="w-full h-12 bg-bx-cyan text-[#0B1121] hover:bg-bx-cyan/90 font-display font-bold tracking-wider hover:shadow-[0_0_24px_rgba(0,229,255,0.5)] transition-all"
            data-testid="roulette-bet-button"
          >
            {playing ? "SPINNING…" : "SPIN"}
          </Button>
        </div>
      </div>
    </div>
  );
}
