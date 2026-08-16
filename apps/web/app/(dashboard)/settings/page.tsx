import { getCurrentUser } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export default async function SettingsPage() {
  const user = await getCurrentUser();
  if (!user) return null;

  const mcp = await prisma.mcpConnection.findUnique({
    where: { userId: user.id },
  });

  const isConnected = mcp?.accessToken && mcp.expiresAt && mcp.expiresAt > new Date();

  return (
    <div className="max-w-3xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1">Settings</h1>
        <p className="text-gray-400 text-sm">
          Manage your account and integrations
        </p>
      </div>

      {/* Profile */}
      <div className="mb-6 p-6 rounded-xl bg-white/5 border border-white/10">
        <h2 className="font-semibold mb-4">Profile</h2>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-400">Name</label>
            <div className="text-sm">{user.name || "Not set"}</div>
          </div>
          <div>
            <label className="text-xs text-gray-400">Email</label>
            <div className="text-sm">{user.email}</div>
          </div>
        </div>
      </div>

      {/* Cloudflare Connection */}
      <div className="mb-6 p-6 rounded-xl bg-white/5 border border-white/10">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold">Cloudflare</h2>
          <span
            className={`text-xs px-2 py-1 rounded-full ${
              isConnected
                ? "bg-green-500/10 text-green-400"
                : "bg-gray-500/10 text-gray-400"
            }`}
          >
            {isConnected ? "Connected" : "Not connected"}
          </span>
        </div>

        {isConnected && mcp.accountName && (
          <div className="mb-4 p-3 rounded-lg bg-white/5">
            <div className="text-xs text-gray-400">Account</div>
            <div className="text-sm">{mcp.accountName}</div>
            {mcp.accountId && (
              <div className="text-xs text-gray-500 mt-1 font-mono">
                {mcp.accountId}
              </div>
            )}
          </div>
        )}

        {isConnected ? (
          <div className="flex items-center gap-3">
            <a
              href="/api/auth/cloudflare"
              className="px-4 py-2 text-sm font-medium bg-white/10 hover:bg-white/15 rounded-lg transition-colors"
            >
              Reconnect
            </a>
            <span className="text-xs text-gray-500">
              {mcp.expiresAt && (
                <>
                  Expires{" "}
                  {new Date(mcp.expiresAt).toLocaleDateString()}
                </>
              )}
            </span>
          </div>
        ) : (
          <div>
            <p className="text-xs text-gray-400 mb-4">
              Connect your Cloudflare account to manage tunnels and DNS records.
            </p>
            <a
              href="/api/auth/cloudflare"
              className="inline-block px-4 py-2 text-sm font-medium bg-orange-500 hover:bg-orange-600 text-black rounded-lg transition-colors"
            >
              Connect Cloudflare
            </a>
          </div>
        )}
      </div>

      {/* Danger Zone */}
      <div className="p-6 rounded-xl bg-red-500/5 border border-red-500/20">
        <h2 className="font-semibold text-red-400 mb-4">Danger Zone</h2>
        <p className="text-xs text-gray-400 mb-4">
          Permanently delete your account and all associated data.
        </p>
        <button className="px-4 py-2 text-sm font-medium bg-red-500/10 hover:bg-red-500/20 text-red-400 rounded-lg transition-colors">
          Delete Account
        </button>
      </div>
    </div>
  );
}
