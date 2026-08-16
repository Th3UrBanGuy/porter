import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { prisma } from "@/lib/prisma";
import { sendCommandToConnector } from "@/lib/ws-client";
import { CloudflareClient } from "@/lib/cloudflare";

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // Get user from DB
  const user = await prisma.user.findUnique({ where: { clerkId: userId } });
  if (!user) {
    return NextResponse.json({ error: "User not found" }, { status: 404 });
  }

  const { subdomain, domain, port, connectorId } = await req.json();

  if (!subdomain || !domain || !port || !connectorId) {
    return NextResponse.json({ error: "Missing fields" }, { status: 400 });
  }

  // Check connector belongs to user and is online
  const connector = await prisma.connector.findFirst({
    where: { id: connectorId, userId: user.id },
  });

  if (!connector) {
    return NextResponse.json(
      { error: "Connector not found" },
      { status: 404 }
    );
  }

  if (connector.status !== "online") {
    return NextResponse.json(
      { error: "Connector is offline" },
      { status: 400 }
    );
  }

  // Check subdomain uniqueness
  const existing = await prisma.tunnel.findUnique({
    where: { subdomain_domain: { subdomain, domain } },
  });

  if (existing) {
    return NextResponse.json(
      { error: "Subdomain already in use" },
      { status: 409 }
    );
  }

  // Get Cloudflare client for this user
  const cf = await CloudflareClient.fromUserId(user.id);
  if (!cf) {
    return NextResponse.json(
      { error: "Cloudflare not connected" },
      { status: 400 }
    );
  }

  // Create tunnel record in DB first
  const tunnel = await prisma.tunnel.create({
    data: {
      userId: user.id,
      connectorId,
      subdomain,
      domain,
      port: parseInt(port),
      status: "creating",
    },
  });

  // Send create command to connector
  try {
    await sendCommandToConnector(
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
  } catch (err: any) {
    console.error("Failed to send create command:", err.message);
    await prisma.tunnel.update({
      where: { id: tunnel.id },
      data: { status: "error" },
    });
    return NextResponse.json(
      { error: "Failed to reach connector" },
      { status: 500 }
    );
  }

  // Create DNS CNAME record (pointing to tunnel)
  try {
    const mcp = await prisma.mcpConnection.findUnique({
      where: { userId: user.id },
    });

    if (mcp?.accountId) {
      const cfAccountId = mcp.accountId;
      const tunnelUrl = `${subdomain}.${domain}`;

      // Create CNAME pointing to the tunnel
      await cf.createDNSRecord(
        mcp.accountId,
        "CNAME",
        tunnelUrl,
        `${tunnel.id}.cfargotunnel.com`,
        true
      );

      console.log(`Created DNS record: ${tunnelUrl} -> ${tunnel.id}.cfargotunnel.com`);
    }
  } catch (err: any) {
    console.error("DNS creation failed:", err.message);
    // Don't fail tunnel creation if DNS fails - can be retried later
  }

  return NextResponse.json({
    success: true,
    tunnel: {
      id: tunnel.id,
      subdomain: tunnel.subdomain,
      domain: tunnel.domain,
      port: tunnel.port,
      status: tunnel.status,
      url: `https://${tunnel.subdomain}.${tunnel.domain}`,
    },
  });
}
