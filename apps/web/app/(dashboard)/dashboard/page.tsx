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

  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-bold mb-1">Dashboard</h1>
      <p className="text-gray-400 text-sm mb-8">
        Welcome back, {user.name || "there"}
      </p>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {[
          {
            label: "Total Tunnels",
            value: tunnelCount,
            icon: "◉",
            href: "/tunnels",
          },
          {
            label: "Active Tunnels",
            value: activeTunnels,
            icon: "●",
            href: "/tunnels",
            highlight: true,
          },
          {
            label: "Connectors",
            value: connectorCount,
            icon: "◎",
            href: "/connectors",
          },
          {
            label: "Online",
            value: onlineConnectors,
            icon: "◆",
            href: "/connectors",
            highlight: onlineConnectors > 0,
          },
        ].map((stat) => (
          <Link
            key={stat.label}
            href={stat.href}
            className="p-4 rounded-xl bg-white/5 border border-white/10 hover:border-white/20 transition-colors"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-400">{stat.label}</span>
              <span className="text-lg">{stat.icon}</span>
            </div>
            <div
              className={`text-3xl font-bold ${
                stat.highlight ? "text-green-400" : ""
              }`}
            >
              {stat.value}
            </div>
          </Link>
        ))}
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
        <Link
          href="/tunnels"
          className="p-4 rounded-xl bg-orange-500/10 border border-orange-500/20 hover:bg-orange-500/15 transition-colors"
        >
          <div className="font-semibold text-orange-400 mb-1">
            Create Tunnel
          </div>
          <div className="text-xs text-gray-400">
            Expose a local service to the internet
          </div>
        </Link>
        <Link
          href="/connectors"
          className="p-4 rounded-xl bg-white/5 border border-white/10 hover:border-white/20 transition-colors"
        >
          <div className="font-semibold mb-1">Install Connector</div>
          <div className="text-xs text-gray-400">
            Connect a new machine to Porter
          </div>
        </Link>
      </div>

      {/* Recent Tunnels */}
      <div className="rounded-xl bg-white/5 border border-white/10">
        <div className="p-4 border-b border-white/10 flex items-center justify-between">
          <h2 className="font-semibold">Recent Tunnels</h2>
          <Link
            href="/tunnels"
            className="text-xs text-orange-400 hover:text-orange-300"
          >
            View all
          </Link>
        </div>
        <div className="divide-y divide-white/5">
          {recentTunnels.length === 0 ? (
            <div className="p-8 text-center text-gray-500 text-sm">
              No tunnels yet. Create one from the{" "}
              <Link href="/tunnels" className="text-orange-400">
                Tunnels
              </Link>{" "}
              page.
            </div>
          ) : (
            recentTunnels.map((tunnel) => (
              <div
                key={tunnel.id}
                className="p-4 flex items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      tunnel.status === "active"
                        ? "bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.5)]"
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
                <span
                  className={`text-xs px-2 py-1 rounded-full ${
                    tunnel.status === "active"
                      ? "bg-green-500/10 text-green-400"
                      : "bg-gray-500/10 text-gray-400"
                  }`}
                >
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
