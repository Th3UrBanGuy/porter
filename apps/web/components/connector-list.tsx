"use client";

import { useState } from "react";
import { useConnectorStatus } from "@/hooks/use-connector-status";

interface Connector {
  id: string;
  name: string;
  status: string;
  lastSeen: string | null;
  token?: string;
}

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
      {/* New connector token display */}
      {newToken && (
        <div className="mb-6 p-4 rounded-xl bg-green-500/10 border border-green-500/20">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-green-400">
              Connector Created
            </h3>
            <button
              onClick={() => setNewToken(null)}
              className="text-xs text-gray-400 hover:text-white"
            >
              Dismiss
            </button>
          </div>
          <p className="text-xs text-gray-400 mb-3">
            Run this command on your machine:
          </p>
          <code className="block p-3 rounded-lg bg-black/50 text-sm text-green-400 font-mono break-all">
            npx porter-connect --token {newToken}
          </code>
        </div>
      )}

      {/* Install instructions */}
      <div className="mb-6 p-4 rounded-xl bg-white/5 border border-white/10">
        <h3 className="text-sm font-semibold mb-2">Install a connector</h3>
        <p className="text-xs text-gray-400 mb-3">
          Run this command on the machine you want to expose services from:
        </p>
        <code className="block p-3 rounded-lg bg-black/50 text-sm text-green-400 font-mono">
          npx porter-connect --token &lt;your-token&gt;
        </code>
      </div>

      {/* Connector list */}
      <div className="rounded-xl bg-white/5 border border-white/10">
        <div className="divide-y divide-white/5">
          {connectors.length === 0 ? (
            <div className="p-12 text-center text-gray-500 text-sm">
              <div className="text-3xl mb-3">◎</div>
              No connectors installed.
              <br />
              Install one to start creating tunnels.
            </div>
          ) : (
            connectors.map((connector) => (
              <div
                key={connector.id}
                className="p-4 flex items-center justify-between hover:bg-white/[0.02] transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      connector.status === "online"
                        ? "bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.5)]"
                        : "bg-gray-500"
                    }`}
                  />
                  <div>
                    <div className="text-sm font-medium">{connector.name}</div>
                    <div className="text-xs text-gray-500">
                      {connector.status === "online"
                        ? "Connected"
                        : "Offline"}
                      {connector.lastSeen &&
                        ` · Last seen ${new Date(
                          connector.lastSeen
                        ).toLocaleDateString()}`}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => deleteConnector(connector.id)}
                  className="text-xs text-gray-400 hover:text-red-400 transition-colors"
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
