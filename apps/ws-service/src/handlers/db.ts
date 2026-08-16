import { PrismaClient } from "@porter/database/src/generated/prisma";
import { PrismaNeon } from "@prisma/adapter-neon";

let prisma: PrismaClient;

function getPrisma() {
  if (!prisma) {
    const adapter = new PrismaNeon({
      connectionString: process.env.DATABASE_URL!,
    });
    prisma = new PrismaClient({ adapter });
  }
  return prisma;
}

export async function updateConnectorStatus(
  connectorId: string,
  status: string
) {
  try {
    await getPrisma().connector.update({
      where: { id: connectorId },
      data: { status },
    });
  } catch (err) {
    console.error(`[DB] Failed to update connector status:`, err);
  }
}

export async function updateConnectorLastSeen(connectorId: string) {
  try {
    await getPrisma().connector.update({
      where: { id: connectorId },
      data: { lastSeen: new Date() },
    });
  } catch (err) {
    console.error(`[DB] Failed to update connector lastSeen:`, err);
  }
}

export async function updateTunnelStatus(
  tunnelId: string,
  status: string,
  url?: string
) {
  try {
    await getPrisma().tunnel.update({
      where: { id: tunnelId },
      data: {
        status,
        ...(url ? { url } : {}),
      },
    });
  } catch (err) {
    console.error(`[DB] Failed to update tunnel status:`, err);
  }
}

export async function getTunnel(tunnelId: string) {
  try {
    return await getPrisma().tunnel.findUnique({
      where: { id: tunnelId },
      include: { connector: true, user: true },
    });
  } catch (err) {
    console.error(`[DB] Failed to get tunnel:`, err);
    return null;
  }
}
