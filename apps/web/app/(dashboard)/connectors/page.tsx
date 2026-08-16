import { getCurrentUser } from "@/lib/auth";
import { ConnectorList } from "@/components/connector-list";

export default async function ConnectorsPage() {
  const user = await getCurrentUser();
  if (!user) return null;

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight">Connectors</h1>
        <p className="text-sm text-zinc-500 mt-1">
          Manage your device connectors
        </p>
      </div>

      <ConnectorList />
    </div>
  );
}
