import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { prisma } from "@/lib/prisma";

const CF_CLIENT_ID = process.env.CF_CLIENT_ID!;
const CF_CLIENT_SECRET = process.env.CF_CLIENT_SECRET!;
const CF_REDIRECT_URI = process.env.CF_REDIRECT_URI || `${process.env.NEXT_PUBLIC_APP_URL}/api/auth/cloudflare/callback`;

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

  // Verify state matches
  const mcp = await prisma.mcpConnection.findUnique({ where: { userId } });
  if (!mcp || mcp.state !== state) {
    return NextResponse.redirect(
      new URL("/settings?error=invalid_state", req.url)
    );
  }

  // Exchange code for tokens
  const tokenRes = await fetch("https://dash.cloudflare.com/oauth2/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code,
      redirect_uri: CF_REDIRECT_URI,
      client_id: CF_CLIENT_ID,
      client_secret: CF_CLIENT_SECRET,
    }),
  });

  if (!tokenRes.ok) {
    const err = await tokenRes.text();
    console.error("Token exchange failed:", err);
    return NextResponse.redirect(
      new URL("/settings?error=token_exchange_failed", req.url)
    );
  }

  const tokens = await tokenRes.json();

  // Get account info
  const accountRes = await fetch("https://api.cloudflare.com/client/v4/accounts", {
    headers: { Authorization: `Bearer ${tokens.access_token}` },
  });

  let accountId = "";
  let accountName = "";
  if (accountRes.ok) {
    const accountData = await accountRes.json();
    if (accountData.result && accountData.result.length > 0) {
      accountId = accountData.result[0].id;
      accountName = accountData.result[0].name;
    }
  }

  // Store tokens in DB
  const expiresAt = new Date(Date.now() + tokens.expires_in * 1000);
  await prisma.mcpConnection.upsert({
    where: { userId },
    update: {
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      expiresAt,
      accountId,
      accountName,
      state: null,
    },
    create: {
      userId,
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      expiresAt,
      accountId,
      accountName,
      state: null,
    },
  });

  return NextResponse.redirect(
    new URL("/settings?connected=cloudflare", req.url)
  );
}
