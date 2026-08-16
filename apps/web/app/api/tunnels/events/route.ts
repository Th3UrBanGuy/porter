import { NextRequest } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { prisma } from "@/lib/prisma";

export async function GET(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return new Response("Unauthorized", { status: 401 });
  }

  const stream = new ReadableStream({
    start(controller) {
      async function sendUpdates() {
        try {
          const tunnels = await prisma.tunnel.findMany({
            where: { userId: userId! },
            include: { connector: true },
          });

          const data = JSON.stringify({ tunnels });
          controller.enqueue(`data: ${data}\n\n`);
        } catch (err) {
          console.error("SSE error:", err);
        }
      }

      // Send initial update
      sendUpdates();

      // Poll every 3 seconds
      const interval = setInterval(sendUpdates, 3000);

      req.signal.addEventListener("abort", () => {
        clearInterval(interval);
        controller.close();
      });
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
