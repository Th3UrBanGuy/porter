"use client";

import { useState } from "react";

interface CreateTunnelFormProps {
  connectors: Array<{ id: string; name: string; status: string }>;
  onCreated: () => void;
}

export function CreateTunnelForm({ connectors, onCreated }: CreateTunnelFormProps) {
  const [subdomain, setSubdomain] = useState("");
  const [port, setPort] = useState("");
  const [connectorId, setConnectorId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onlineConnectors = connectors.filter((c) => c.status === "online");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await fetch("/api/tunnels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subdomain,
          domain: "kalandar.me",
          port: parseInt(port),
          connectorId,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Failed to create tunnel");
        return;
      }

      setSubdomain("");
      setPort("");
      setConnectorId("");
      onCreated();
    } catch {
      setError("Network error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div>
          <label className="block text-xs text-zinc-500 uppercase tracking-wider mb-2">Subdomain</label>
          <input
            type="text"
            value={subdomain}
            onChange={(e) => setSubdomain(e.target.value)}
            placeholder="myapp"
            className="w-full px-3 py-2.5 text-sm bg-[#09090b] border border-white/10 rounded-lg focus:outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20 text-white placeholder-zinc-600 transition-all"
            required
            pattern="[a-z0-9-]+"
          />
        </div>
        <div>
          <label className="block text-xs text-zinc-500 uppercase tracking-wider mb-2">Port</label>
          <input
            type="number"
            value={port}
            onChange={(e) => setPort(e.target.value)}
            placeholder="3000"
            className="w-full px-3 py-2.5 text-sm bg-[#09090b] border border-white/10 rounded-lg focus:outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20 text-white placeholder-zinc-600 transition-all"
            required
            min="1"
            max="65535"
          />
        </div>
        <div>
          <label className="block text-xs text-zinc-500 uppercase tracking-wider mb-2">Connector</label>
          <select
            value={connectorId}
            onChange={(e) => setConnectorId(e.target.value)}
            className="w-full px-3 py-2.5 text-sm bg-[#09090b] border border-white/10 rounded-lg focus:outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20 text-white transition-all"
            required
          >
            <option value="">Select connector</option>
            {onlineConnectors.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="text-xs text-red-400 bg-red-500/10 px-3 py-2 rounded-lg">{error}</div>
      )}

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={loading || onlineConnectors.length === 0}
          className="px-5 py-2.5 text-sm font-semibold bg-orange-500 hover:bg-orange-600 text-black rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? "Creating..." : "Create Tunnel"}
        </button>
        {onlineConnectors.length === 0 && connectors.length > 0 && (
          <p className="text-xs text-yellow-500">No connectors online</p>
        )}
      </div>
    </form>
  );
}
