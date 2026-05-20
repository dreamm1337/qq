import React from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "@/components/Sidebar";
import Header from "@/components/Header";
import LiveFeed from "@/components/LiveFeed";

export default function Layout() {
  return (
    <div className="min-h-screen grain bg-[#0B1121] text-white">
      <Sidebar />
      <div className="lg:pl-[260px]">
        <Header />
        <main className="px-4 sm:px-6 lg:px-10 py-6 lg:pr-[340px]" data-testid="main-content">
          <Outlet />
        </main>
        <LiveFeed />
      </div>
    </div>
  );
}
