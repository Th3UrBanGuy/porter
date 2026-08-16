import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export async function DELETE(
  _req: Request,
  { params }: { params: { id: string } }
) {
  const user = await getCurrentUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const connector = await prisma.connector.findFirst({
    where: { id: params.id, userId: user.id },
  });

  if (!connector) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  await prisma.connector.delete({ where: { id: params.id } });

  return NextResponse.json({ success: true });
}
