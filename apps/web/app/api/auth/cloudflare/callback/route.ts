import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { prisma } from "@/lib/prisma";
import { cfMCP } from "@/lib/cloudflare";

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.redirect(new URL("/sign-in", req.url));
  }

  const url = new URL(req.url);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const error = url.searchParams.get("error");

  if (error) {
    return NextResponse.redirect(
      new URL(`/settings?error=${encodeURIComponent(error)}`, req.url)
    );
  }

  if (!code || !state) {
    return NextResponse.redirect(
      new URL("/settings?error=missing_code", req.url)
    );
  }

  const mcp = await prisma.mcpConnection.findUnique({ where: { userId } });
  if (!mcp || mcp.state !== state) {
    return NextResponse.redirect(
      new URL("/settings?error=invalid_state", req.url)
    );
  }

  try {
    const clientInfo = mcp.clientInfo as any || {};
    const tokens = await cfMCP.exchangeCode(
      code,
      state,
      mcp.state!,
      mcp.codeVerifier!,
      clientInfo
    );

    // Get account info via MCP
    let accountId = "";
    try {
      accountId = await cfMCP.getAccountId(userId);
    } catch (e) {
      console.log("Could not detect account ID:", e);
    }

    await prisma.mcpConnection.upsert({
      where: { userId },
      update: {
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token || null,
        expiresAt: new Date(tokens.expires_at!),
        state: null,
        codeVerifier: null,
        accountId: accountId || null,
      },
      create: {
        userId,
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token || null,
        expiresAt: new Date(tokens.expires_at!),
        accountId: accountId || null,
      },
    });

    return NextResponse.redirect(
      new URL("/settings?connected=cloudflare", req.url)
    );
  } catch (err: any) {
    console.error("Token exchange failed:", err);
    return NextResponse.redirect(
      new URL(`/settings?error=${encodeURIComponent(err.message)}`, req.url)
    );
  }
}
