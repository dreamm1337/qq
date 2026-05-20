import React from "react";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { LogOut, Wallet, User as UserIcon } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

export default function Header() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const onLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <header className="bx-glass sticky top-0 z-20 px-4 sm:px-6 lg:px-10 h-16 flex items-center justify-between" data-testid="app-header">
      <div className="lg:hidden font-display font-black text-lg">
        <span className="text-bx-cyan">BET</span> DREAM
      </div>

      <div className="flex-1" />

      <div className="flex items-center gap-3">
        <div
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#131A2A] border border-[#1E293B]"
          data-testid="header-balance"
        >
          <Wallet size={16} className="text-bx-gold" />
          <span className="font-mono font-bold text-bx-gold tabular-nums">
            {user ? Number(user.balance).toFixed(2) : "0.00"}
          </span>
          <span className="text-xs text-bx-muted">coins</span>
        </div>

        <Link to="/history" className="hidden sm:inline-flex">
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#131A2A] border border-[#1E293B] hover:border-bx-cyan/50 transition-colors">
            <UserIcon size={16} className="text-bx-cyan" />
            <span className="font-display text-xs tracking-wide" data-testid="header-username">{user?.username}</span>
            {user?.role === "admin" && (
              <span className="text-[9px] uppercase tracking-widest px-1.5 py-0.5 rounded bg-bx-purple/20 text-bx-purple border border-bx-purple/30">
                Admin
              </span>
            )}
          </div>
        </Link>

        <Button
          variant="ghost"
          size="sm"
          onClick={onLogout}
          className="text-bx-muted hover:text-bx-red hover:bg-[#131A2A]"
          data-testid="logout-button"
        >
          <LogOut size={16} />
        </Button>
      </div>
    </header>
  );
}
