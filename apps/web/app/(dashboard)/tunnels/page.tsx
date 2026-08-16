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
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight">Tunnels</h1>
        <p className="text-sm text-zinc-500 mt-1">
          Manage your Cloudflare tunnels
        </p>
      </div>

      {/* Create tunnel */}
      <div className="mb-8 p-6 rounded-xl bg-white/[0.02] border border-white/5">
        <h2 className="font-semibold mb-4">Create Tunnel</h2>
        <CreateTunnelForm connectors={connectors} onCreated={() => {}} />
      </div>

      {/* Tunnel list */}
      <div className="rounded-xl bg-white/[0.02] border border-white/5">
        <div className="px-5 py-4 border-b border-white/5">
          <h2 className="font-semibold">Active Tunnels</h2>
        </div>
        <TunnelList />
      </div>
    </div>
  );
}
