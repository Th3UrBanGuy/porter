import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { prisma } from "@/lib/prisma";
import { cfMCP } from "@/lib/cloudflare";

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const { url, state, codeVerifier } = await cfMCP.generateAuthUrl();

    // Store state + codeVerifier + clientInfo in DB for callback
    await prisma.mcpConnection.upsert({
      where: { userId },
      update: { state, codeVerifier },
      create: {
        userId,
        accessToken: "",
        refreshToken: "",
        expiresAt: new Date(0),
        state,
        codeVerifier,
      },
    });

    return NextResponse.redirect(url);
  } catch (err: any) {
    console.error("OAuth initiation failed:", err);
    return NextResponse.redirect(
      new URL(`/settings?error=${encodeURIComponent(err.message)}`, req.url)
    );
  }
}
