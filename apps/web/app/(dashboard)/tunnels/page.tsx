import { getCurrentUser } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { TunnelList } from "@/components/tunnel-list";
import { CreateTunnelForm } from "@/components/create-tunnel-form";

export default async function TunnelsPage() {
  const user = await getCurrentUser();
  if (!user) return null;

  const connectors = await prisma.connector.findMany({
    where: { userId: user.id },
    select: { id: true, name: true, status: true },
  });

  return (
    <div className="max-w-5xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1">Tunnels</h1>
        <p className="text-gray-400 text-sm">
          Manage your Cloudflare tunnels
        </p>
      </div>

      {/* Create tunnel form */}
      <div className="mb-8 p-6 rounded-xl bg-white/5 border border-white/10">
        <h2 className="font-semibold mb-4">Create Tunnel</h2>
        <CreateTunnelForm connectors={connectors} onCreated={() => {}} />
      </div>

      {/* Tunnel list */}
      <div className="rounded-xl bg-white/5 border border-white/10">
        <div className="p-4 border-b border-white/10">
          <h2 className="font-semibold">Active Tunnels</h2>
        </div>
        <TunnelList />
      </div>
    </div>
  );
}
