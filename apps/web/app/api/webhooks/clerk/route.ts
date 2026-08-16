import { Webhook } from "svix";
import { headers } from "next/headers";
import { prisma } from "@/lib/prisma";

export async function POST(req: Request) {
  const SIGNING_SECRET = process.env.CLERK_WEBHOOK_SIGNING_SECRET;

  if (!SIGNING_SECRET) {
    throw new Error("Missing CLERK_WEBHOOK_SIGNING_SECRET");
  }

  const headerPayload = await headers();
  const svix_id = headerPayload.get("svix-id");
  const svix_timestamp = headerPayload.get("svix-timestamp");
  const svix_signature = headerPayload.get("svix-signature");

  if (!svix_id || !svix_timestamp || !svix_signature) {
    return Response.json({ error: "Missing Svix headers" }, { status: 400 });
  }

  const payload = await req.json();
  const body = JSON.stringify(payload);

  const wh = new Webhook(SIGNING_SECRET);

  let evt: { type: string; data: Record<string, unknown> };
  try {
    evt = wh.verify(body, {
      "svix-id": svix_id,
      "svix-timestamp": svix_timestamp,
      "svix-signature": svix_signature,
    }) as { type: string; data: Record<string, unknown> };
  } catch (err) {
    console.error("Webhook verification failed:", err);
    return Response.json({ error: "Verification failed" }, { status: 400 });
  }

  const eventType = evt.type;
  const data = evt.data;

  if (eventType === "user.created") {
    const email = (data.email_addresses as Array<{ email_address: string }>)?.[0]?.email_address ?? "";
    const firstName = data.first_name as string | null;
    const lastName = data.last_name as string | null;

    await prisma.user.create({
      data: {
        clerkId: data.id as string,
        email,
        name: [firstName, lastName].filter(Boolean).join(" ") || null,
      },
    });
  }

  if (eventType === "user.updated") {
    const email = (data.email_addresses as Array<{ email_address: string }>)?.[0]?.email_address ?? "";
    const firstName = data.first_name as string | null;
    const lastName = data.last_name as string | null;

    await prisma.user.update({
      where: { clerkId: data.id as string },
      data: {
        email,
        name: [firstName, lastName].filter(Boolean).join(" ") || null,
      },
    });
  }

  if (eventType === "user.deleted") {
    await prisma.user.delete({
      where: { clerkId: data.id as string },
    });
  }

  return Response.json({ received: true });
}
