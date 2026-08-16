import { io, Socket } from "socket.io-client";
import { spawn, ChildProcess } from "child_process";
import { checkPort } from "./ports";

const runningTunnels = new Map<string, ChildProcess>();

export function startConnector(token: string, wsUrl: string) {
  console.log(`[porter] Connecting to ${wsUrl}...`);

  const socket: Socket = io(wsUrl, {
    auth: { token },
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 30000,
    timeout: 10000,
  });

  socket.on("connect", () => {
    console.log("[porter] ✓ Connected to portal");
    console.log("[porter] Waiting for commands...\n");

    // Send heartbeat every 30s
    setInterval(() => {
      socket.emit("heartbeat");
    }, 30000);
  });

  socket.on("disconnect", (reason) => {
    console.log(`[porter] ✗ Disconnected: ${reason}`);
  });

  socket.on("connect_error", (err) => {
    console.error(`[porter] Connection error: ${err.message}`);
  });

  // Handle commands from portal
  socket.on("command", async (data: any) => {
    const { type, payload, requestId } = data;
    console.log(`[porter] → Received command: ${type}`);

    try {
      switch (type) {
        case "create_tunnel":
          await handleCreateTunnel(socket, requestId, payload);
          break;
        case "stop_tunnel":
          await handleStopTunnel(socket, requestId, payload);
          break;
        case "scan_ports":
          await handleScanPorts(socket, requestId);
          break;
        case "get_status":
          await handleGetStatus(socket, requestId);
          break;
        default:
          console.log(`[porter] Unknown command: ${type}`);
          socket.emit("response", {
            type: "error",
            requestId,
            payload: { message: `Unknown command: ${type}` },
          });
      }
    } catch (err: any) {
      console.error(`[porter] Error handling ${type}:`, err.message);
      socket.emit("response", {
        type: "error",
        requestId,
        payload: { message: err.message },
      });
    }
  });
}

async function handleCreateTunnel(
  socket: Socket,
  requestId: string,
  payload: any
) {
  const { tunnelId, subdomain, domain, port, tunnelToken } = payload;

  console.log(`[porter] Creating tunnel: ${subdomain}.${domain} → localhost:${port}`);

  // Check if port is accessible
  const portOpen = await checkPort(port);
  if (!portOpen) {
    console.log(`[porter] ⚠ Port ${port} is not open, but proceeding anyway`);
  }

  // Check if cloudflared is installed
  const cloudflaredPath = await findCloudflared();
  if (!cloudflaredPath) {
    throw new Error(
      "cloudflared not found. Install it from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
    );
  }

  // Kill existing tunnel for this tunnelId if any
  const existingProcess = runningTunnels.get(tunnelId);
  if (existingProcess) {
    existingProcess.kill("SIGTERM");
    runningTunnels.delete(tunnelId);
  }

  // Start cloudflared
  const args = ["tunnel", "--no-autoupdate", "run"];
  if (tunnelToken) {
    args.push("--token", tunnelToken);
  }

  console.log(`[porter] Starting cloudflared: ${cloudflaredPath} ${args.join(" ")}`);

  const child = spawn(cloudflaredPath, args, {
    stdio: ["ignore", "pipe", "pipe"],
    detached: true,
  });

  runningTunnels.set(tunnelId, child);

  // Handle stdout
  child.stdout?.on("data", (data: Buffer) => {
    const msg = data.toString().trim();
    if (msg) {
      console.log(`[porter] cloudflared: ${msg}`);
    }
  });

  // Handle stderr
  child.stderr?.on("data", (data: Buffer) => {
    const msg = data.toString().trim();
    if (msg && !msg.includes("INF")) {
      console.log(`[porter] cloudflared: ${msg}`);
    }
  });

  // Handle process exit
  child.on("exit", (code) => {
    console.log(`[porter] cloudflared exited with code ${code}`);
    runningTunnels.delete(tunnelId);

    // Report to portal
    socket.emit("response", {
      type: "tunnel_stopped",
      requestId,
      payload: { tunnelId },
    });
  });

  // Wait a moment for cloudflared to start
  await new Promise((resolve) => setTimeout(resolve, 2000));

  // Check if process is still running
  if (child.exitCode !== null) {
    throw new Error(`cloudflared failed to start (exit code: ${child.exitCode})`);
  }

  const url = `https://${subdomain}.${domain}`;
  console.log(`[porter] ✓ Tunnel active: ${url}`);

  // Report success to portal
  socket.emit("response", {
    type: "tunnel_active",
    requestId,
    payload: {
      tunnelId,
      url,
      pid: child.pid,
    },
  });
}

async function handleStopTunnel(
  socket: Socket,
  requestId: string,
  payload: any
) {
  const { tunnelId } = payload;

  console.log(`[porter] Stopping tunnel: ${tunnelId}`);

  const process = runningTunnels.get(tunnelId);
  if (process) {
    process.kill("SIGTERM");
    runningTunnels.delete(tunnelId);
    console.log(`[porter] ✓ Tunnel stopped`);
  } else {
    console.log(`[porter] No running process for tunnel ${tunnelId}`);
  }

  socket.emit("response", {
    type: "tunnel_stopped",
    requestId,
    payload: { tunnelId },
  });
}

async function handleScanPorts(socket: Socket, requestId: string) {
  console.log(`[porter] Scanning ports...`);

  const commonPorts = [
    80, 443, 3000, 3001, 4000, 4200, 5000, 5173, 5500, 6000,
    6379, 7262, 8000, 8080, 8443, 8888, 9000, 9090,
  ];

  const openPorts: number[] = [];
  const checks = commonPorts.map(async (port) => {
    const isOpen = await checkPort(port);
    if (isOpen) openPorts.push(port);
  });

  await Promise.all(checks);
  openPorts.sort((a, b) => a - b);

  console.log(`[porter] Open ports: ${openPorts.join(", ") || "none"}`);

  socket.emit("response", {
    type: "ports_scan",
    requestId,
    payload: { ports: openPorts },
  });
}

async function handleGetStatus(socket: Socket, requestId: string) {
  const tunnels = Array.from(runningTunnels.entries()).map(([id, proc]) => ({
    tunnelId: id,
    pid: proc.pid,
    running: proc.exitCode === null,
  }));

  socket.emit("response", {
    type: "status_update",
    requestId,
    payload: { tunnels, hostname: require("os").hostname() },
  });
}

async function findCloudflared(): Promise<string | null> {
  const { execSync } = require("child_process");

  // Check common locations
  const paths = [
    "cloudflared",
    "/usr/local/bin/cloudflared",
    "/usr/bin/cloudflared",
  ];

  for (const p of paths) {
    try {
      execSync(`which ${p}`, { stdio: "ignore" });
      return p;
    } catch {}
  }

  return null;
}
