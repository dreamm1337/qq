import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

export default function Register() {
  const { register, user } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  if (user) {
    navigate("/");
  }

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    const res = await register(email, username, password);
    setLoading(false);
    if (res.ok) {
      toast.success("Welcome to Bet Dream! 1000 coins on the house.");
      navigate("/");
    } else {
      toast.error(res.error || "Registration failed");
    }
  };

  return (
    <div className="min-h-screen bg-[#0B1121] grain flex items-center justify-center px-4">
      <div className="absolute inset-0 pointer-events-none opacity-50"
        style={{
          backgroundImage: "radial-gradient(at 30% 20%, rgba(0,229,255,0.15), transparent 50%), radial-gradient(at 80% 80%, rgba(176,38,255,0.12), transparent 50%)",
        }}
      />
      <div className="relative w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="font-display text-4xl font-black tracking-tighter">
            <span className="text-bx-cyan bx-text-glow">BET</span> DREAM
          </div>
          <div className="text-xs uppercase tracking-[0.4em] text-bx-muted mt-2">demo casino</div>
        </div>

        <form
          onSubmit={submit}
          className="bx-card p-8 space-y-5 animate-rise"
          data-testid="register-form"
        >
          <h1 className="font-display text-2xl font-bold">Create Account</h1>
          <p className="text-sm text-bx-muted -mt-2">Get 1000 free demo coins on signup.</p>

          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">Username</label>
            <Input
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="bg-[#0B1121] border-[#1E293B] focus-visible:ring-bx-cyan h-11"
              placeholder="player123"
              minLength={2}
              maxLength={24}
              data-testid="register-username-input"
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">Email</label>
            <Input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="bg-[#0B1121] border-[#1E293B] focus-visible:ring-bx-cyan h-11"
              placeholder="you@betdream.com"
              data-testid="register-email-input"
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-bx-muted font-bold">Password</label>
            <Input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="bg-[#0B1121] border-[#1E293B] focus-visible:ring-bx-cyan h-11"
              placeholder="••••••••"
              minLength={4}
              data-testid="register-password-input"
            />
          </div>

          <Button
            type="submit"
            disabled={loading}
            className="w-full h-11 bg-bx-cyan text-[#0B1121] hover:bg-bx-cyan/90 font-display font-bold tracking-wider hover:shadow-[0_0_24px_rgba(0,229,255,0.5)] transition-all"
            data-testid="register-submit-button"
          >
            {loading ? "CREATING…" : "CREATE ACCOUNT"}
          </Button>

          <div className="text-center text-sm text-bx-muted">
            Have an account?{" "}
            <Link to="/login" className="text-bx-cyan hover:underline" data-testid="register-login-link">
              Sign in
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
