import { getCurrentUser } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export default async function SettingsPage() {
  const user = await getCurrentUser();
  if (!user) return null;

  const mcp = await prisma.mcpConnection.findUnique({
    where: { userId: user.id },
  });

  const cloudConnected =
    mcp?.accessToken && mcp.expiresAt && mcp.expiresAt > new Date();

  return (
    <div className="max-w-2xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-zinc-500 mt-1">
          Manage your account and integrations
        </p>
      </div>

      {/* Profile */}
      <div className="mb-6 p-6 rounded-xl bg-white/[0.02] border border-white/5">
        <h2 className="font-semibold mb-4">Profile</h2>
        <div className="space-y-4">
          <div>
            <label className="text-xs text-zinc-500 uppercase tracking-wider">Name</label>
            <div className="text-sm mt-1">{user.name || "Not set"}</div>
          </div>
          <div>
            <label className="text-xs text-zinc-500 uppercase tracking-wider">Email</label>
            <div className="text-sm mt-1">{user.email}</div>
          </div>
        </div>
      </div>

      {/* Cloudflare Connection */}
      <div className="mb-6 p-6 rounded-xl bg-white/[0.02] border border-white/5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold">Cloudflare</h2>
          <span
            className={`text-xs px-2.5 py-1 rounded-full ${
              cloudConnected
                ? "bg-emerald-500/10 text-emerald-400"
                : "bg-zinc-500/10 text-zinc-400"
            }`}
          >
            {cloudConnected ? "Connected" : "Not connected"}
          </span>
        </div>

        {cloudConnected && mcp.accountId && (
          <div className="mb-4 p-3 rounded-lg bg-white/[0.02] border border-white/5">
            <div className="text-xs text-zinc-500">Account ID</div>
            <div className="text-sm font-mono mt-1">{mcp.accountId}</div>
          </div>
        )}

        {cloudConnected ? (
          <div className="flex items-center gap-3">
            <a
              href="/api/auth/cloudflare"
              className="px-4 py-2 text-sm font-medium bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg transition-colors"
            >
              Reconnect
            </a>
            {mcp.expiresAt && (
              <span className="text-xs text-zinc-500">
                Expires {new Date(mcp.expiresAt).toLocaleDateString()}
              </span>
            )}
          </div>
        ) : (
          <div>
            <p className="text-sm text-zinc-400 mb-4">
              Connect your Cloudflare account to manage tunnels and DNS records.
            </p>
            <a
              href="/api/auth/cloudflare"
              className="inline-block px-4 py-2 text-sm font-semibold bg-orange-500 hover:bg-orange-600 text-black rounded-lg transition-colors"
            >
              Connect Cloudflare
            </a>
          </div>
        )}
      </div>

      {/* Danger Zone */}
      <div className="p-6 rounded-xl bg-red-500/5 border border-red-500/10">
        <h2 className="font-semibold text-red-400 mb-2">Danger Zone</h2>
        <p className="text-sm text-zinc-500 mb-4">
          Permanently delete your account and all associated data.
        </p>
        <button className="px-4 py-2 text-sm font-medium bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 rounded-lg transition-colors">
          Delete Account
        </button>
      </div>
    </div>
  );
}
