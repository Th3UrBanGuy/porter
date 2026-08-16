"use client";

import { useState } from "react";
import { useTunnelStatus } from "@/hooks/use-tunnel-status";

interface Tunnel {
  id: string;
  subdomain: string;
  domain: string;
  port: number;
  status: string;
  url: string | null;
  connector: { name: string; status: string };
  createdAt: string;
}

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
      <div className="p-12 text-center text-gray-500 text-sm">
        <div className="text-3xl mb-3">◉</div>
        No tunnels yet.
        <br />
        Create one to expose a local service.
      </div>
    );
  }

  return (
    <div className="divide-y divide-white/5">
      {tunnels.map((tunnel) => (
        <div
          key={tunnel.id}
          className="p-4 flex items-center justify-between hover:bg-white/[0.02] transition-colors"
        >
          <div className="flex items-center gap-3">
            <div
              className={`w-2 h-2 rounded-full ${
                tunnel.status === "active"
                  ? "bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.5)]"
                  : tunnel.status === "error"
                  ? "bg-red-400"
                  : "bg-gray-500"
              }`}
            />
            <div>
              <div className="text-sm font-medium">
                {tunnel.subdomain}.{tunnel.domain}
              </div>
              <div className="text-xs text-gray-500">
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
                className="text-xs text-orange-400 hover:text-orange-300 transition-colors"
              >
                {tunnel.url}
              </a>
            )}
            <span
              className={`text-xs px-2 py-1 rounded-full ${
                tunnel.status === "active"
                  ? "bg-green-500/10 text-green-400"
                  : tunnel.status === "error"
                  ? "bg-red-500/10 text-red-400"
                  : "bg-gray-500/10 text-gray-400"
              }`}
            >
              {tunnel.status}
            </span>
            {tunnel.status === "active" && (
              <button
                onClick={() => stopTunnel(tunnel.id)}
                className="text-xs text-gray-400 hover:text-red-400 transition-colors"
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
