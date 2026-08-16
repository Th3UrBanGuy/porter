import { io } from "socket.io-client";

const WS_URL = process.env.WS_SERVICE_URL || "http://localhost:3001";

// Client-side socket for sending commands to the WS service
let wsClient: ReturnType<typeof io> | null = null;

function getWsClient() {
  if (!wsClient) {
    wsClient = io(WS_URL, {
      auth: { serverKey: process.env.WS_SERVER_KEY || "porter-server" },
    });
  }
  return wsClient;
}

// Send a command to a specific connector via the WS service
export function sendCommandToConnector(
  connectorId: string,
  type: string,
  payload: Record<string, unknown>,
  timeoutMs = 30000
): Promise<any> {
  return new Promise((resolve, reject) => {
    const client = getWsClient();
    const requestId = `api_${Date.now()}_${Math.random().toString(36).slice(2)}`;

    const timeout = setTimeout(() => {
      reject(new Error(`Command "${type}" timed out`));
    }, timeoutMs);

    // Listen for response
    const responseHandler = (data: any) => {
      if (data.requestId === requestId) {
        clearTimeout(timeout);
        client.off("response", responseHandler);
        resolve(data);
      }
    };
    client.on("response", responseHandler);

    // Send command
    client.emit("command", {
      targetConnectorId: connectorId,
      type,
      payload,
      requestId,
    });
  });
}

// Check if a connector is online
export function isConnectorOnline(connectorId: string): Promise<boolean> {
  return new Promise((resolve) => {
    const client = getWsClient();
    const requestId = `check_${Date.now()}`;

    const timeout = setTimeout(() => resolve(false), 5000);

    const responseHandler = (data: any) => {
      if (data.requestId === requestId) {
        clearTimeout(timeout);
        client.off("response", responseHandler);
        resolve(true);
      }
    };
    client.on("response", responseHandler);

    client.emit("command", {
      targetConnectorId: connectorId,
      type: "get_status",
      payload: {},
      requestId,
    });
  });
}
