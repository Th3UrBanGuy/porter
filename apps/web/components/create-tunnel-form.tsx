"use client";

import { useState } from "react";

interface CreateTunnelFormProps {
  connectors: Array<{ id: string; name: string; status: string }>;
  onCreated: () => void;
}

export function CreateTunnelForm({
  connectors,
  onCreated,
}: CreateTunnelFormProps) {
  const [subdomain, setSubdomain] = useState("");
  const [port, setPort] = useState("");
  const [connectorId, setConnectorId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      // For now, use a default domain. Will be replaced with user's domain
      const res = await fetch("/api/tunnels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subdomain,
          domain: "porter.dev", // TODO: Get from user's Cloudflare connection
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
    } catch (err) {
      setError("Network error");
    } finally {
      setLoading(false);
    }
  }

  const onlineConnectors = connectors.filter((c) => c.status === "online");

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div>
          <label className="block text-xs text-gray-400 mb-1">Subdomain</label>
          <input
            type="text"
            value={subdomain}
            onChange={(e) => setSubdomain(e.target.value)}
            placeholder="myapp"
            className="w-full px-3 py-2 text-sm bg-white/5 border border-white/10 rounded-lg focus:outline-none focus:border-orange-500/50 text-white placeholder-gray-500"
            required
            pattern="[a-z0-9-]+"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Port</label>
          <input
            type="number"
            value={port}
            onChange={(e) => setPort(e.target.value)}
            placeholder="3000"
            className="w-full px-3 py-2 text-sm bg-white/5 border border-white/10 rounded-lg focus:outline-none focus:border-orange-500/50 text-white placeholder-gray-500"
            required
            min="1"
            max="65535"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Connector</label>
          <select
            value={connectorId}
            onChange={(e) => setConnectorId(e.target.value)}
            className="w-full px-3 py-2 text-sm bg-white/5 border border-white/10 rounded-lg focus:outline-none focus:border-orange-500/50 text-white"
            required
          >
            <option value="">Select connector</option>
            {onlineConnectors.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="text-xs text-red-400 bg-red-500/10 px-3 py-2 rounded-lg">
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={loading || onlineConnectors.length === 0}
        className="px-4 py-2 text-sm font-medium bg-orange-500 hover:bg-orange-600 text-black rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? "Creating..." : "Create Tunnel"}
      </button>

      {onlineConnectors.length === 0 && connectors.length > 0 && (
        <p className="text-xs text-yellow-400">
          No connectors online. Start a connector on your machine first.
        </p>
      )}
    </form>
  );
}
