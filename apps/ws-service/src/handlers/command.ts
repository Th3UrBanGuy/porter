import { Server, Socket } from "socket.io";
import { updateTunnelStatus } from "./db";

// Store pending requests (requestId → { resolve, timeout })
const pendingRequests = new Map<
  string,
  {
    resolve: (data: any) => void;
    timeout: NodeJS.Timeout;
  }
>();

// Send a command to a connector and wait for response
export function sendCommandAndWait(
  io: Server,
  socketId: string,
  type: string,
  payload: Record<string, unknown>,
  timeoutMs = 30000
): Promise<any> {
  return new Promise((resolve, reject) => {
    const requestId = `req_${Date.now()}_${Math.random().toString(36).slice(2)}`;

    const timeout = setTimeout(() => {
      pendingRequests.delete(requestId);
      reject(new Error(`Command "${type}" timed out after ${timeoutMs}ms`));
    }, timeoutMs);

    pendingRequests.set(requestId, { resolve, timeout });

    io.to(socketId).emit("command", {
      type,
      payload,
      requestId,
    });
  });
}

// Handle responses from connectors
export async function handleResponse(
  io: Server,
  connectorId: string,
  userId: string,
  data: any
) {
  const { type, payload, requestId } = data;

  console.log(`[WS] Response from ${connectorId}: ${type}`);

  // Check if this is a response to a pending request
  if (requestId && pendingRequests.has(requestId)) {
    const pending = pendingRequests.get(requestId)!;
    clearTimeout(pending.timeout);
    pendingRequests.delete(requestId);
    pending.resolve({ type, payload });
    return;
  }

  // Handle standalone events (not tied to a request)
  switch (type) {
    case "tunnel_active": {
      const { tunnelId, url } = payload;
      await updateTunnelStatus(tunnelId as string, "active", url as string);
      // Notify the user's dashboard via WebSocket
      io.to(`user:${userId}`).emit("tunnel:status", {
        tunnelId,
        status: "active",
        url,
      });
      break;
    }

    case "tunnel_stopped": {
      const { tunnelId } = payload;
      await updateTunnelStatus(tunnelId as string, "inactive");
      io.to(`user:${userId}`).emit("tunnel:status", {
        tunnelId,
        status: "inactive",
      });
      break;
    }

    case "tunnel_error": {
      const { tunnelId, message } = payload;
      await updateTunnelStatus(tunnelId as string, "error");
      io.to(`user:${userId}`).emit("tunnel:status", {
        tunnelId,
        status: "error",
        error: message,
      });
      break;
    }

    case "ports_scan": {
      // Forward to requesting socket if needed
      break;
    }

    default:
      console.log(`[WS] Unknown response type: ${type}`);
  }
}
