import React, { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Shield, TrendingUp, TrendingDown, Minus } from "lucide-react";

export default function Admin() {
  const [users, setUsers] = useState([]);
  const [bets, setBets] = useState([]);
  const [stats, setStats] = useState(null);
  const [tab, setTab] = useState("users");
  const [editing, setEditing] = useState(null); // user id being edited
  const [editAmount, setEditAmount] = useState("");
  const [editMode, setEditMode] = useState("set");

  const load = async () => {
    const [u, b, s] = await Promise.all([
      api.get("/admin/users"),
      api.get("/admin/bets"),
      api.get("/admin/stats"),
    ]);
    setUsers(u.data);
    setBets(b.data);
    setStats(s.data);
  };

  useEffect(() => { load(); }, []);

  const setRigging = async (userId, rigging) => {
    try {
      await api.patch(`/admin/users/${userId}/rigging`, { rigging });
      toast.success(`Rigging set to ${rigging}`);
      load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Failed");
    }
  };

  const saveBalance = async (userId) => {
    try {
      await api.patch(`/admin/users/${userId}/balance`, {
        mode: editMode,
        amount: Number(editAmount),
      });
      toast.success("Balance updated");
      setEditing(null);
      setEditAmount("");
      load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Failed");
    }
  };

  return (
    <div className="space-y-6" data-testid="admin-page">
      <div className="flex items-center gap-3">
        <Shield className="text-bx-purple" />
        <h1 className="font-display text-3xl font-black tracking-tight">Admin Panel</h1>
      </div>

      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          <Stat label="Users" value={stats.total_users} />
          <Stat label="Bets" value={stats.total_bets} />
          <Stat label="Wagered" value={stats.total_wagered.toFixed(2)} />
          <Stat label="Paid Out" value={stats.total_paid_out.toFixed(2)} accent="text-bx-gold" />
          <Stat
            label="House Profit"
            value={(stats.house_profit >= 0 ? "+" : "") + stats.house_profit.toFixed(2)}
            accent={stats.house_profit >= 0 ? "text-bx-green" : "text-bx-red"}
          />
        </div>
      )}

      <div className="flex gap-2 border-b border-[#1E293B]">
        {["users", "bets"].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            data-testid={`admin-tab-${t}`}
            className={`px-5 py-3 text-sm font-display uppercase tracking-wider border-b-2 transition-colors ${
              tab === t ? "text-bx-purple border-bx-purple" : "text-bx-muted border-transparent hover:text-white"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "users" && (
        <div className="bx-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-bx-muted border-b border-[#1E293B]">
                  <th className="px-5 py-3">User</th>
                  <th className="px-5 py-3">Email</th>
                  <th className="px-5 py-3">Balance</th>
                  <th className="px-5 py-3">Rigging</th>
                  <th className="px-5 py-3 w-[280px]">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1E293B]">
                {users.map((u) => (
                  <tr key={u.id} data-testid={`admin-user-row-${u.id}`}>
                    <td className="px-5 py-3 font-display">
                      {u.username}
                      {u.role === "admin" && (
                        <span className="ml-2 text-[9px] uppercase tracking-widest px-1.5 py-0.5 rounded bg-bx-purple/20 text-bx-purple">
                          admin
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3 text-bx-muted font-mono text-xs">{u.email}</td>
                    <td className="px-5 py-3 font-mono font-bold text-bx-gold">{u.balance.toFixed(2)}</td>
                    <td className="px-5 py-3">
                      <RigBadge value={u.rigging} />
                    </td>
                    <td className="px-5 py-3">
                      {editing === u.id ? (
                        <div className="flex items-center gap-2">
                          <select
                            value={editMode}
                            onChange={(e) => setEditMode(e.target.value)}
                            className="bg-[#0B1121] border border-[#1E293B] rounded px-2 py-1.5 text-xs"
                            data-testid={`admin-edit-mode-${u.id}`}
                          >
                            <option value="set">Set</option>
                            <option value="add">Add</option>
                          </select>
                          <Input
                            type="number"
                            value={editAmount}
                            onChange={(e) => setEditAmount(e.target.value)}
                            className="h-8 w-24 bg-[#0B1121] border-[#1E293B] font-mono text-xs"
                            placeholder="0.00"
                            data-testid={`admin-edit-input-${u.id}`}
                          />
                          <Button size="sm" onClick={() => saveBalance(u.id)} className="h-8 bg-bx-cyan text-[#0B1121] hover:bg-bx-cyan/90" data-testid={`admin-edit-save-${u.id}`}>
                            Save
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setEditing(null)} className="h-8 text-bx-muted">
                            ×
                          </Button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5">
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-8 bg-transparent border-[#1E293B] hover:border-bx-cyan/60 hover:text-bx-cyan text-xs"
                            onClick={() => { setEditing(u.id); setEditAmount(u.balance.toFixed(2)); setEditMode("set"); }}
                            data-testid={`admin-edit-balance-${u.id}`}
                          >
                            Balance
                          </Button>
                          <RigButton current={u.rigging} value="win" onClick={() => setRigging(u.id, "win")} testid={`admin-rig-win-${u.id}`}>
                            <TrendingUp size={12} /> Win
                          </RigButton>
                          <RigButton current={u.rigging} value="none" onClick={() => setRigging(u.id, "none")} testid={`admin-rig-none-${u.id}`}>
                            <Minus size={12} /> Fair
                          </RigButton>
                          <RigButton current={u.rigging} value="lose" onClick={() => setRigging(u.id, "lose")} testid={`admin-rig-lose-${u.id}`}>
                            <TrendingDown size={12} /> Lose
                          </RigButton>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "bets" && (
        <div className="bx-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-bx-muted border-b border-[#1E293B]">
                  <th className="px-5 py-3">Time</th>
                  <th className="px-5 py-3">User</th>
                  <th className="px-5 py-3">Game</th>
                  <th className="px-5 py-3">Bet</th>
                  <th className="px-5 py-3">Mult</th>
                  <th className="px-5 py-3">Payout</th>
                  <th className="px-5 py-3">Result</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1E293B]">
                {bets.map((b) => (
                  <tr key={b.id} data-testid="admin-bet-row">
                    <td className="px-5 py-2 text-xs font-mono text-bx-muted">{new Date(b.created_at).toLocaleString()}</td>
                    <td className="px-5 py-2 font-display text-sm">{b.username}</td>
                    <td className="px-5 py-2 capitalize text-sm">{b.game}</td>
                    <td className="px-5 py-2 font-mono text-sm">{b.amount.toFixed(2)}</td>
                    <td className="px-5 py-2 font-mono text-xs">{b.multiplier.toFixed(2)}x</td>
                    <td className="px-5 py-2 font-mono text-sm text-bx-gold">{b.payout.toFixed(2)}</td>
                    <td className="px-5 py-2">
                      <span
                        className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded font-bold ${
                          b.result === "win" ? "bg-bx-green/15 text-bx-green" : "bg-bx-red/15 text-bx-red"
                        }`}
                      >
                        {b.result}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, accent = "text-white" }) {
  return (
    <div className="bx-card p-4">
      <div className="text-[10px] uppercase tracking-widest text-bx-muted font-bold">{label}</div>
      <div className={`font-mono font-bold text-xl mt-1 ${accent}`}>{value}</div>
    </div>
  );
}

function RigBadge({ value }) {
  const map = {
    none: "bg-[#0B1121] text-bx-muted border-[#1E293B]",
    win: "bg-bx-green/15 text-bx-green border-bx-green/40",
    lose: "bg-bx-red/15 text-bx-red border-bx-red/40",
  };
  return (
    <span className={`text-[10px] uppercase tracking-wider px-2 py-1 rounded font-bold border ${map[value]}`}>
      {value === "none" ? "fair" : value}
    </span>
  );
}

function RigButton({ current, value, onClick, children, testid }) {
  const active = current === value;
  const colorMap = {
    win: active ? "bg-bx-green/20 border-bx-green text-bx-green" : "hover:border-bx-green/60 hover:text-bx-green",
    lose: active ? "bg-bx-red/20 border-bx-red text-bx-red" : "hover:border-bx-red/60 hover:text-bx-red",
    none: active ? "bg-white/10 border-white text-white" : "hover:border-white/60 hover:text-white",
  };
  return (
    <button
      onClick={onClick}
      data-testid={testid}
      className={`flex items-center gap-1 px-2 py-1.5 rounded text-[11px] uppercase tracking-wider font-bold border border-[#1E293B] bg-transparent transition-colors ${colorMap[value]}`}
    >
      {children}
    </button>
  );
}
