import { NextResponse } from "next/server";

// TODO: Implement Cloudflare MCP OAuth flow
// This will follow the same pattern as v1 (PKCE + dynamic client registration)

export async function GET() {
  return NextResponse.json({
    status: "not_implemented",
    message: "Cloudflare MCP OAuth coming soon",
  });
}
