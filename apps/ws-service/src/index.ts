import dotenv from "dotenv";
dotenv.config();

import { Server } from "socket.io";
import { verifyConnectorToken } from "./auth";
import { handleCommand, handleResponse } from "./handlers/command";
import { updateConnectorStatus, updateConnectorLastSeen } from "./handlers/db";

const PORT = parseInt(process.env.PORT || "3001");
const ALLOWED_ORIGINS = process.env.ALLOWED_ORIGINS?.split(",") || [
  "http://localhost:3000",
];

const io = new Server(PORT, {
  cors: {
    origin: ALLOWED_ORIGINS,
    methods: ["GET", "POST"],
  },
  pingInterval: 25000,
  pingTimeout: 60000,
});

// Track online connectors
const onlineConnectors = new Map<string, string>(); // connectorId → socketId

io.use(async (socket, next) => {
  const token = socket.handshake.auth.token;
  if (!token) {
    return next(new Error("Authentication required"));
  }

  try {
    const connector = await verifyConnectorToken(token);
    if (!connector) {
      return next(new Error("Invalid token"));
    }

    (socket as any).connectorId = connector.id;
    (socket as any).userId = connector.userId;
    (socket as any).connectorName = connector.name;
    next();
  } catch (err) {
    next(new Error("Authentication failed"));
  }
});

io.on("connection", async (socket) => {
  const connectorId = (socket as any).connectorId as string;
  const userId = (socket as any).userId as string;
  const connectorName = (socket as any).connectorName as string;

  console.log(
    `[WS] Connector "${connectorName}" (${connectorId}) connected (user: ${userId})`
  );

  // Track online status
  onlineConnectors.set(connectorId, socket.id);

  // Update database
  await updateConnectorStatus(connectorId, "online");
  await updateConnectorLastSeen(connectorId);

  // Join user room for broadcasting
  socket.join(`user:${userId}`);

  // Handle commands from connector (responses to portal commands)
  socket.on("response", async (data) => {
    await handleResponse(io, connectorId, userId, data);
  });

  // Handle heartbeat
  socket.on("heartbeat", async () => {
    await updateConnectorLastSeen(connectorId);
  });

  // Handle disconnect
  socket.on("disconnect", async (reason) => {
    console.log(
      `[WS] Connector "${connectorName}" (${connectorId}) disconnected: ${reason}`
    );
    onlineConnectors.delete(connectorId);
    await updateConnectorStatus(connectorId, "offline");
  });
});

// Export for API routes to send commands to connectors
export function sendCommandToConnector(
  userId: string,
  connectorId: string,
  type: string,
  payload: Record<string, unknown>,
  requestId: string
): boolean {
  const socketId = onlineConnectors.get(connectorId);
  if (!socketId) {
    console.log(`[WS] Connector ${connectorId} is not online`);
    return false;
  }

  io.to(socketId).emit("command", {
    type,
    payload,
    requestId,
  });

  console.log(`[WS] Sent command "${type}" to connector ${connectorId}`);
  return true;
}

// Export for checking connector status
export function isConnectorOnline(connectorId: string): boolean {
  return onlineConnectors.has(connectorId);
}

// Export for API to get online connectors for a user
export function getOnlineConnectorsForUser(userId: string): string[] {
  const room = io.sockets.adapter.rooms.get(`user:${userId}`);
  if (!room) return [];

  const connectorIds: string[] = [];
  for (const socketId of room) {
    for (const [cId, sId] of onlineConnectors.entries()) {
      if (sId === socketId) {
        connectorIds.push(cId);
      }
    }
  }
  return connectorIds;
}

console.log(`[WS] WebSocket service running on port ${PORT}`);
