import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { sendCommandToConnector } from "@/lib/ws-client";

export async function GET() {
  const user = await getCurrentUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const tunnels = await prisma.tunnel.findMany({
    where: { userId: user.id },
    orderBy: { createdAt: "desc" },
    include: { connector: true },
  });

  return NextResponse.json({ tunnels });
}

export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { subdomain, domain, port, connectorId } = await req.json();

  if (!subdomain || !domain || !port || !connectorId) {
    return NextResponse.json(
      { error: "Missing required fields" },
      { status: 400 }
    );
  }

  // Validate subdomain format
  if (!/^[a-z0-9-]+$/.test(subdomain)) {
    return NextResponse.json(
      { error: "Subdomain must be lowercase alphanumeric with hyphens" },
      { status: 400 }
    );
  }

  // Verify connector belongs to user
  const connector = await prisma.connector.findFirst({
    where: { id: connectorId, userId: user.id },
  });

  if (!connector) {
    return NextResponse.json({ error: "Connector not found" }, { status: 404 });
  }

  // Check for existing tunnel with same subdomain/domain
  const existing = await prisma.tunnel.findUnique({
    where: { subdomain_domain: { subdomain, domain } },
  });

  if (existing) {
    return NextResponse.json(
      { error: "Subdomain already in use" },
      { status: 409 }
    );
  }

  // Create tunnel record
  const tunnel = await prisma.tunnel.create({
    data: {
      userId: user.id,
      connectorId,
      subdomain,
      domain,
      port: parseInt(port),
      url: `https://${subdomain}.${domain}`,
      status: "inactive",
    },
  });

  // Send command to connector via WebSocket
  try {
    const result = await sendCommandToConnector(
      connectorId,
      "create_tunnel",
      {
        tunnelId: tunnel.id,
        subdomain,
        domain,
        port: parseInt(port),
      },
      30000
    );

    // Update tunnel status based on response
    if (result.type === "tunnel_active") {
      await prisma.tunnel.update({
        where: { id: tunnel.id },
        data: { status: "active" },
      });

      return NextResponse.json({
        tunnel: {
          ...tunnel,
          status: "active",
          url: result.payload.url,
        },
      });
    } else {
      await prisma.tunnel.update({
        where: { id: tunnel.id },
        data: { status: "error" },
      });

      return NextResponse.json(
        { error: result.payload?.message || "Failed to create tunnel" },
        { status: 500 }
      );
    }
  } catch (err: any) {
    // Connector might be offline — tunnel stays inactive
    console.error("Failed to send command to connector:", err.message);

    return NextResponse.json({
      tunnel,
      warning: "Connector is offline. Tunnel will activate when connector connects.",
    });
  }
}
