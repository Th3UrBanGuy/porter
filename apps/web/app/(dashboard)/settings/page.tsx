import { getCurrentUser } from "@/lib/auth";

export default async function SettingsPage() {
  const user = await getCurrentUser();
  if (!user) return null;

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold mb-1">Settings</h1>
      <p className="text-gray-400 text-sm mb-8">Manage your account</p>

      {/* Profile */}
      <div className="rounded-xl bg-white/5 border border-white/10 p-6 mb-6">
        <h2 className="font-semibold mb-4">Profile</h2>
        <div className="space-y-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Name</label>
            <div className="text-sm">{user.name || "Not set"}</div>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Email</label>
            <div className="text-sm">{user.email}</div>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">User ID</label>
            <div className="text-xs font-mono text-gray-500">{user.id}</div>
          </div>
        </div>
      </div>

      {/* Cloudflare Connection */}
      <div className="rounded-xl bg-white/5 border border-white/10 p-6 mb-6">
        <h2 className="font-semibold mb-4">Cloudflare</h2>
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-gray-500" />
          <span className="text-sm text-gray-400">Not connected</span>
          <button className="ml-auto px-4 py-2 text-sm font-medium bg-orange-500 hover:bg-orange-600 text-black rounded-lg transition-colors">
            Connect Cloudflare
          </button>
        </div>
      </div>

      {/* Danger Zone */}
      <div className="rounded-xl border border-red-500/20 p-6">
        <h2 className="font-semibold text-red-400 mb-2">Danger Zone</h2>
        <p className="text-xs text-gray-400 mb-4">
          Permanently delete your account and all associated data.
        </p>
        <button className="px-4 py-2 text-sm font-medium bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 rounded-lg transition-colors">
          Delete Account
        </button>
      </div>
    </div>
  );
}
