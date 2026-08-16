import { getCurrentUser } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import Link from "next/link";

export default async function DashboardPage() {
  const user = await getCurrentUser();
  if (!user) return null;

  const [tunnelCount, connectorCount, activeTunnels, onlineConnectors] =
    await Promise.all([
      prisma.tunnel.count({ where: { userId: user.id } }),
      prisma.connector.count({ where: { userId: user.id } }),
      prisma.tunnel.count({ where: { userId: user.id, status: "active" } }),
      prisma.connector.count({ where: { userId: user.id, status: "online" } }),
    ]);

  const recentTunnels = await prisma.tunnel.findMany({
    where: { userId: user.id },
    orderBy: { createdAt: "desc" },
    take: 5,
    include: { connector: true },
  });

  const mcp = await prisma.mcpConnection.findUnique({
    where: { userId: user.id },
  });
  const cloudConnected = mcp?.accessToken && mcp.expiresAt && mcp.expiresAt > new Date();

  return (
    <div>
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-sm text-zinc-500 mt-1">
          Welcome back, {user.name || "there"}
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {[
          { label: "Total Tunnels", value: tunnelCount, href: "/tunnels" },
          { label: "Active", value: activeTunnels, href: "/tunnels", color: "text-emerald-400" },
          { label: "Connectors", value: connectorCount, href: "/connectors" },
          { label: "Online", value: onlineConnectors, href: "/connectors", color: "text-emerald-400" },
        ].map((stat) => (
          <Link
            key={stat.label}
            href={stat.href}
            className="p-5 rounded-xl bg-white/[0.02] border border-white/5 hover:border-white/10 transition-colors"
          >
            <div className="text-xs text-zinc-500 uppercase tracking-wider mb-2">{stat.label}</div>
            <div className={`text-3xl font-bold ${stat.color || ""}`}>{stat.value}</div>
          </Link>
        ))}
      </div>

      {/* Quick actions */}
      <div className="grid sm:grid-cols-2 gap-4 mb-8">
        <Link
          href="/tunnels"
          className="group p-5 rounded-xl bg-gradient-to-br from-orange-500/10 to-orange-600/5 border border-orange-500/20 hover:border-orange-500/30 transition-colors"
        >
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-orange-500/20 flex items-center justify-center text-orange-500">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
            </div>
            <div>
              <div className="font-semibold text-orange-500">Create Tunnel</div>
              <div className="text-xs text-zinc-500">Expose a local service</div>
            </div>
          </div>
        </Link>

        <Link
          href="/connectors"
          className="group p-5 rounded-xl bg-white/[0.02] border border-white/5 hover:border-white/10 transition-colors"
        >
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center text-zinc-400 group-hover:text-white transition-colors">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m0-7.172a4 4 0 015.656 0l4 4a4 4 0 01-5.656 5.656l-1.102-1.101" />
              </svg>
            </div>
            <div>
              <div className="font-semibold">Install Connector</div>
              <div className="text-xs text-zinc-500">Connect a new machine</div>
            </div>
          </div>
        </Link>
      </div>

      {/* Cloudflare status */}
      {!cloudConnected && (
        <div className="mb-8 p-4 rounded-xl bg-yellow-500/5 border border-yellow-500/20">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-yellow-500/10 flex items-center justify-center text-yellow-500">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
            </div>
            <div className="flex-1">
              <div className="text-sm font-medium">Cloudflare not connected</div>
              <div className="text-xs text-zinc-500">Connect your Cloudflare account to create tunnels</div>
            </div>
            <Link
              href="/settings"
              className="px-4 py-2 text-sm font-medium bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg transition-colors"
            >
              Connect
            </Link>
          </div>
        </div>
      )}

      {/* Recent Tunnels */}
      <div className="rounded-xl bg-white/[0.02] border border-white/5">
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/5">
          <h2 className="font-semibold">Recent Tunnels</h2>
          <Link href="/tunnels" className="text-xs text-orange-500 hover:text-orange-400 font-medium">
            View all
          </Link>
        </div>
        <div className="divide-y divide-white/5">
          {recentTunnels.length === 0 ? (
            <div className="p-12 text-center">
              <div className="w-12 h-12 rounded-xl bg-white/5 flex items-center justify-center mx-auto mb-4 text-zinc-600">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m0-7.172a4 4 0 015.656 0l4 4a4 4 0 01-5.656 5.656l-1.102-1.101" />
                </svg>
              </div>
              <p className="text-sm text-zinc-500">No tunnels yet</p>
              <Link href="/tunnels" className="inline-block mt-3 text-sm text-orange-500 hover:text-orange-400 font-medium">
                Create your first tunnel
              </Link>
            </div>
          ) : (
            recentTunnels.map((tunnel) => (
              <div key={tunnel.id} className="px-5 py-4 flex items-center justify-between hover:bg-white/[0.02] transition-colors">
                <div className="flex items-center gap-3">
                  <div className={`w-2 h-2 rounded-full ${
                    tunnel.status === "active"
                      ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]"
                      : "bg-zinc-600"
                  }`} />
                  <div>
                    <div className="text-sm font-medium">{tunnel.subdomain}.{tunnel.domain}</div>
                    <div className="text-xs text-zinc-500">Port {tunnel.port} · {tunnel.connector.name}</div>
                  </div>
                </div>
                <span className={`text-xs px-2.5 py-1 rounded-full ${
                  tunnel.status === "active"
                    ? "bg-emerald-500/10 text-emerald-400"
                    : "bg-zinc-500/10 text-zinc-400"
                }`}>
                  {tunnel.status}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
