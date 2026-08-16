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

export async function verifyConnectorToken(token: string) {
  const connector = await getPrisma().connector.findUnique({
    where: { token },
    select: { id: true, userId: true, name: true },
  });

  return connector;
}
