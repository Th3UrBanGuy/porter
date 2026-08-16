"use client";

import { useState } from "react";
import { useTunnelStatus } from "@/hooks/use-tunnel-status";

export function TunnelList() {
  const { tunnels, refresh } = useTunnelStatus();

  async function stopTunnel(id: string) {
    try {
      await fetch(`/api/tunnels/${id}`, { method: "POST" });
      refresh();
    } catch (err) {
      console.error("Failed to stop tunnel:", err);
    }
  }

  if (tunnels.length === 0) {
    return (
      <div className="p-12 text-center">
        <div className="w-12 h-12 rounded-xl bg-white/5 flex items-center justify-center mx-auto mb-4 text-zinc-600">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m0-7.172a4 4 0 015.656 0l4 4a4 4 0 01-5.656 5.656l-1.102-1.101" />
          </svg>
        </div>
        <p className="text-sm text-zinc-500">No tunnels yet</p>
        <p className="text-xs text-zinc-600 mt-1">Create one to expose a local service</p>
      </div>
    );
  }

  return (
    <div className="divide-y divide-white/5">
      {tunnels.map((tunnel) => (
        <div
          key={tunnel.id}
          className="px-5 py-4 flex items-center justify-between hover:bg-white/[0.02] transition-colors"
        >
          <div className="flex items-center gap-3">
            <div
              className={`w-2 h-2 rounded-full ${
                tunnel.status === "active"
                  ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]"
                  : tunnel.status === "error"
                  ? "bg-red-400"
                  : "bg-zinc-600"
              }`}
            />
            <div>
              <div className="text-sm font-medium">
                {tunnel.subdomain}.{tunnel.domain}
              </div>
              <div className="text-xs text-zinc-500">
                Port {tunnel.port} · {tunnel.connector.name}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {tunnel.url && tunnel.status === "active" && (
              <a
                href={tunnel.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-orange-500 hover:text-orange-400 transition-colors"
              >
                {tunnel.url}
              </a>
            )}
            <span
              className={`text-xs px-2.5 py-1 rounded-full ${
                tunnel.status === "active"
                  ? "bg-emerald-500/10 text-emerald-400"
                  : tunnel.status === "error"
                  ? "bg-red-500/10 text-red-400"
                  : "bg-zinc-500/10 text-zinc-400"
              }`}
            >
              {tunnel.status}
            </span>
            {tunnel.status === "active" && (
              <button
                onClick={() => stopTunnel(tunnel.id)}
                className="text-xs text-zinc-500 hover:text-red-400 transition-colors"
              >
                Stop
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
