import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { prisma } from "@/lib/prisma";
import { sendCommandToConnector } from "@/lib/ws-client";
import { cfMCP } from "@/lib/cloudflare";

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const user = await prisma.user.findUnique({ where: { clerkId: userId } });
  if (!user) {
    return NextResponse.json({ error: "User not found" }, { status: 404 });
  }

  const { subdomain, domain, port, connectorId } = await req.json();

  if (!subdomain || !domain || !port || !connectorId) {
    return NextResponse.json({ error: "Missing fields" }, { status: 400 });
  }

  // Check connector
  const connector = await prisma.connector.findFirst({
    where: { id: connectorId, userId: user.id },
  });
  if (!connector) {
    return NextResponse.json({ error: "Connector not found" }, { status: 404 });
  }
  if (connector.status !== "online") {
    return NextResponse.json({ error: "Connector is offline" }, { status: 400 });
  }

  // Check subdomain uniqueness
  const existing = await prisma.tunnel.findUnique({
    where: { subdomain_domain: { subdomain, domain } },
  });
  if (existing) {
    return NextResponse.json({ error: "Subdomain already in use" }, { status: 409 });
  }

  // Check Cloudflare connected
  const mcp = await prisma.mcpConnection.findUnique({ where: { userId: user.id } });
  if (!mcp?.accessToken) {
    return NextResponse.json({ error: "Cloudflare not connected" }, { status: 400 });
  }

  // Create tunnel record
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

  const fullDomain = `${subdomain}.${domain}`;

  try {
    // Get zone ID
    const zoneId = await cfMCP.getZoneId(user.id, domain);

    // Clean up any existing DNS records for this subdomain
    try {
      const existingRecords = await cfMCP.listDNSRecords(user.id, zoneId);
      for (const rec of existingRecords) {
        if (rec.name === fullDomain) {
          await cfMCP.deleteDNSRecord(user.id, zoneId, rec.id);
        }
      }
    } catch {}

    // Create or reuse tunnel
    let tunnelId = "";
    let tunnelToken = "";

    // Check for existing tunnels
    const existingTunnels = await cfMCP.listTunnels(user.id);
    if (existingTunnels.length > 0) {
      tunnelId = existingTunnels[0].id;
      tunnelToken = await cfMCP.getTunnelToken(user.id, tunnelId);
    } else {
      const newTunnel = await cfMCP.createTunnel(user.id, "porter-tunnel");
      tunnelId = newTunnel.id;
      tunnelToken = await cfMCP.getTunnelToken(user.id, tunnelId);
    }

    // Add hostname to tunnel config
    await cfMCP.addTunnelHostname(user.id, tunnelId, fullDomain, `http://localhost:${port}`);

    // Create DNS CNAME record
    await cfMCP.createDNSRecord(
      user.id,
      zoneId,
      "CNAME",
      fullDomain,
      `${tunnelId}.cfargotunnel.com`,
      true
    );

    // Update DB with tunnel info
    await prisma.tunnel.update({
      where: { id: tunnel.id },
      data: {
        cloudflareTunnelId: tunnelId,
        status: "active",
        url: `https://${fullDomain}`,
      },
    });

    // Send create command to connector with tunnel token
    try {
      await sendCommandToConnector(
        connectorId,
        "create_tunnel",
        {
          tunnelId: tunnel.id,
          tunnelToken,
          subdomain,
          domain,
          port: parseInt(port),
        },
        30000
      );
    } catch (err: any) {
      console.error("Failed to send create command:", err.message);
      // Don't fail - tunnel is created in Cloudflare, just connector might need restart
    }

    return NextResponse.json({
      success: true,
      tunnel: {
        id: tunnel.id,
        subdomain: tunnel.subdomain,
        domain: tunnel.domain,
        port: tunnel.port,
        status: "active",
        url: `https://${fullDomain}`,
      },
    });
  } catch (err: any) {
    console.error("Tunnel creation failed:", err);
    await prisma.tunnel.update({
      where: { id: tunnel.id },
      data: { status: "error" },
    });
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
