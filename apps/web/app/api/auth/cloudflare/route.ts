import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { prisma } from "@/lib/prisma";

const CF_CLIENT_ID = process.env.CF_CLIENT_ID!;
const CF_CLIENT_SECRET = process.env.CF_CLIENT_SECRET!;
const CF_REDIRECT_URI = process.env.CF_REDIRECT_URI || `${process.env.NEXT_PUBLIC_APP_URL}/api/auth/cloudflare/callback`;

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // Generate random state for CSRF protection
  const state = crypto.randomUUID();

  // Store state in DB for verification
  await prisma.mcpConnection.upsert({
    where: { userId },
    update: { state },
    create: {
      userId,
      accessToken: "",
      refreshToken: "",
      expiresAt: new Date(0),
      state,
    },
  });

  const authUrl = new URL("https://dash.cloudflare.com/oauth2/auth");
  authUrl.searchParams.set("client_id", CF_CLIENT_ID);
  authUrl.searchParams.set("redirect_uri", CF_REDIRECT_URI);
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("state", state);
  authUrl.searchParams.set("scope", "account:read tunnel:read tunnel:write dns:write zone:read");
  authUrl.searchParams.set("aud", "https://api.cloudflare.com/client/v4");

  return NextResponse.redirect(authUrl.toString());
}
