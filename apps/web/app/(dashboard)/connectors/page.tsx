import { getCurrentUser } from "@/lib/auth";
import { ConnectorList } from "@/components/connector-list";

export default async function ConnectorsPage() {
  const user = await getCurrentUser();
  if (!user) return null;

  return (
    <div className="max-w-5xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1">Connectors</h1>
        <p className="text-gray-400 text-sm">
          Manage your device connectors
        </p>
      </div>

      <ConnectorList />
    </div>
  );
}
