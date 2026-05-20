import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Lobby from "@/pages/Lobby";
import Crash from "@/pages/Crash";
import Mines from "@/pages/Mines";
import Coinflip from "@/pages/Coinflip";
import Roulette from "@/pages/Roulette";
import History from "@/pages/History";
import Admin from "@/pages/Admin";

function Protected({ children, adminOnly = false }) {
  const { user, ready } = useAuth();
  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0B1121]">
        <div className="text-bx-cyan font-display animate-pulse" data-testid="loading-state">Loading…</div>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (adminOnly && user.role !== "admin") return <Navigate to="/" replace />;
  return children;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster position="top-right" theme="dark" richColors />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route
            path="/"
            element={
              <Protected>
                <Layout />
              </Protected>
            }
          >
            <Route index element={<Lobby />} />
            <Route path="crash" element={<Crash />} />
            <Route path="mines" element={<Mines />} />
            <Route path="coinflip" element={<Coinflip />} />
            <Route path="roulette" element={<Roulette />} />
            <Route path="history" element={<History />} />
            <Route
              path="admin"
              element={
                <Protected adminOnly>
                  <Admin />
                </Protected>
              }
            />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
