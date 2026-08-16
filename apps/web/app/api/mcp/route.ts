import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { CloudflareClient } from "@/lib/cloudflare";

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const cf = await CloudflareClient.fromUserId(userId);
  if (!cf) {
    return NextResponse.json(
      { error: "Cloudflare not connected" },
      { status: 400 }
    );
  }

  const { action, params } = await req.json();

  try {
    let result;

    switch (action) {
      case "list_zones":
        result = await cf.listZones();
        break;
      case "list_tunnels":
        result = await cf.listTunnels(params.accountId);
        break;
      case "create_dns":
        result = await cf.createDNSRecord(
          params.zoneId,
          params.type,
          params.name,
          params.content,
          params.proxied
        );
        break;
      case "delete_dns":
        await cf.deleteDNSRecord(params.zoneId, params.recordId);
        result = { success: true };
        break;
      default:
        return NextResponse.json(
          { error: "Unknown action" },
          { status: 400 }
        );
    }

    return NextResponse.json({ success: true, result });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
