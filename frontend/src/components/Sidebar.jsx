import React from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Rocket, Bomb, Coins, CircleDot, Home, History as HistoryIcon, Shield, Building2, Circle, Target, Spade } from "lucide-react";

const navItems = [
  { to: "/", label: "Lobby", icon: Home, end: true, testid: "nav-lobby" },
  { to: "/crash", label: "Crash", icon: Rocket, testid: "nav-crash" },
  { to: "/mines", label: "Mines", icon: Bomb, testid: "nav-mines" },
  { to: "/towers", label: "Towers", icon: Building2, testid: "nav-towers" },
  { to: "/plinko", label: "Plinko", icon: Circle, testid: "nav-plinko" },
  { to: "/blackjack", label: "Blackjack", icon: Spade, testid: "nav-blackjack" },
  { to: "/upgrader", label: "Upgrader", icon: Target, testid: "nav-upgrader" },
  { to: "/coinflip", label: "Coinflip", icon: Coins, testid: "nav-coinflip" },
  { to: "/roulette", label: "Roulette", icon: CircleDot, testid: "nav-roulette" },
  { to: "/history", label: "History", icon: HistoryIcon, testid: "nav-history" },
];

export default function Sidebar() {
  const { user } = useAuth();
  return (
    <aside
      className="hidden lg:flex flex-col fixed inset-y-0 left-0 w-[260px] bg-[#0B1121] border-r border-[#1E293B] z-30"
      data-testid="sidebar"
    >
      <div className="px-6 pt-7 pb-6">
        <div className="font-display text-2xl font-black tracking-tight">
          <span className="text-bx-cyan bx-text-glow">BLOX</span>
          <span className="text-white">FLIP</span>
        </div>
        <div className="text-[10px] uppercase tracking-[0.3em] text-bx-muted mt-1">demo casino</div>
      </div>

      <nav className="flex-1 px-3 space-y-1 overflow-y-auto pb-4">
        {navItems.map(({ to, label, icon: Icon, end, testid }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            data-testid={testid}
            className={({ isActive }) =>
              `group flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
                isActive
                  ? "bg-[#131A2A] text-bx-cyan border border-[#1E293B] shadow-[0_0_18px_rgba(0,229,255,0.18)]"
                  : "text-bx-muted hover:bg-[#131A2A]/60 hover:text-white border border-transparent"
              }`
            }
          >
            <Icon size={17} className="shrink-0" />
            <span className="font-display text-[13px] tracking-wide">{label}</span>
          </NavLink>
        ))}

        {user?.role === "admin" && (
          <NavLink
            to="/admin"
            data-testid="nav-admin"
            className={({ isActive }) =>
              `mt-3 flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
                isActive
                  ? "bg-[#131A2A] text-bx-purple border border-bx-purple/40 shadow-[0_0_18px_rgba(176,38,255,0.25)]"
                  : "text-bx-muted hover:bg-[#131A2A]/60 hover:text-bx-purple border border-transparent"
              }`
            }
          >
            <Shield size={17} />
            <span className="font-display text-[13px] tracking-wide">Admin Panel</span>
          </NavLink>
        )}
      </nav>

      <div className="px-5 pb-5 text-[11px] text-bx-muted">
        © {new Date().getFullYear()} BloxFlip demo
      </div>
    </aside>
  );
}
