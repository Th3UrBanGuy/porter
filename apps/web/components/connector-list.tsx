"use client";

import { useState } from "react";
import { useConnectorStatus } from "@/hooks/use-connector-status";

export function ConnectorList() {
  const { connectors, refresh } = useConnectorStatus();
  const [newToken, setNewToken] = useState<string | null>(null);

  async function createConnector() {
    try {
      const res = await fetch("/api/connectors", { method: "POST" });
      const data = await res.json();
      setNewToken(data.connector.token);
      refresh();
    } catch (err) {
      console.error("Failed to create connector:", err);
    }
  }

  async function deleteConnector(id: string) {
    if (!confirm("Remove this connector?")) return;
    try {
      await fetch(`/api/connectors/${id}`, { method: "DELETE" });
      refresh();
    } catch (err) {
      console.error("Failed to delete connector:", err);
    }
  }

  return (
    <div>
      {/* New connector token */}
      {newToken && (
        <div className="mb-6 p-5 rounded-xl bg-emerald-500/5 border border-emerald-500/20">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-emerald-400">Connector Created</h3>
            <button
              onClick={() => setNewToken(null)}
              className="text-xs text-zinc-500 hover:text-white transition-colors"
            >
              Dismiss
            </button>
          </div>
          <p className="text-xs text-zinc-500 mb-3">Run this command on your machine:</p>
          <div className="flex items-center gap-2">
            <code className="flex-1 p-3 rounded-lg bg-[#09090b] border border-white/5 text-sm text-emerald-400 font-mono break-all">
              npx porter-connect --token {newToken}
            </code>
            <button
              onClick={() => navigator.clipboard.writeText(`npx porter-connect --token ${newToken}`)}
              className="p-3 rounded-lg bg-white/5 hover:bg-white/10 border border-white/5 text-zinc-400 hover:text-white transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Create connector button */}
      <div className="mb-6">
        <button
          onClick={createConnector}
          className="px-4 py-2.5 text-sm font-semibold bg-orange-500 hover:bg-orange-600 text-black rounded-lg transition-colors"
        >
          New Connector
        </button>
      </div>

      {/* Connector list */}
      <div className="rounded-xl bg-white/[0.02] border border-white/5">
        <div className="divide-y divide-white/5">
          {connectors.length === 0 ? (
            <div className="p-12 text-center">
              <div className="w-12 h-12 rounded-xl bg-white/5 flex items-center justify-center mx-auto mb-4 text-zinc-600">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2" />
                </svg>
              </div>
              <p className="text-sm text-zinc-500">No connectors installed</p>
              <p className="text-xs text-zinc-600 mt-1">Create one to start making tunnels</p>
            </div>
          ) : (
            connectors.map((connector) => (
              <div
                key={connector.id}
                className="px-5 py-4 flex items-center justify-between hover:bg-white/[0.02] transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      connector.status === "online"
                        ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]"
                        : "bg-zinc-600"
                    }`}
                  />
                  <div>
                    <div className="text-sm font-medium">{connector.name}</div>
                    <div className="text-xs text-zinc-500">
                      {connector.status === "online" ? "Connected" : "Offline"}
                      {connector.lastSeen &&
                        ` · Last seen ${new Date(connector.lastSeen).toLocaleDateString()}`}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => deleteConnector(connector.id)}
                  className="text-xs text-zinc-500 hover:text-red-400 transition-colors"
                >
                  Remove
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
