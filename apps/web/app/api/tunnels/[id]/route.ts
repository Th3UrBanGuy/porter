import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { sendCommandToConnector } from "@/lib/ws-client";

export async function POST(
  req: Request,
  { params }: { params: { id: string } }
) {
  const user = await getCurrentUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const tunnel = await prisma.tunnel.findFirst({
    where: { id: params.id, userId: user.id },
    include: { connector: true },
  });

  if (!tunnel) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  // Send stop command to connector
  try {
    await sendCommandToConnector(
      tunnel.connectorId,
      "stop_tunnel",
      { tunnelId: tunnel.id },
      10000
    );
  } catch (err: any) {
    console.error("Failed to send stop command:", err.message);
  }

  // Update tunnel status
  await prisma.tunnel.update({
    where: { id: params.id },
    data: { status: "inactive" },
  });

  return NextResponse.json({ success: true });
}
