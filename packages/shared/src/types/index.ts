export type ConnectorStatus = "online" | "offline" | "error";
export type TunnelStatus = "active" | "inactive" | "error";

export interface CreateTunnelRequest {
  subdomain: string;
  domain: string;
  port: number;
  connectorId: string;
}

export interface TunnelResponse {
  id: string;
  subdomain: string;
  domain: string;
  port: number;
  status: TunnelStatus;
  url: string | null;
  connectorId: string;
  createdAt: string;
}

export interface ConnectorInfo {
  id: string;
  name: string;
  status: ConnectorStatus;
  lastSeen: string | null;
  metadata?: {
    os?: string;
    ip?: string;
    version?: string;
    hostname?: string;
  };
}

export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: string;
}

export interface WSCommand {
  type: "create_tunnel" | "stop_tunnel" | "get_status" | "scan_ports";
  payload: Record<string, unknown>;
  requestId: string;
}

export interface WSResponse {
  type: "tunnel_active" | "tunnel_stopped" | "status_update" | "ports_scan" | "error";
  payload: Record<string, unknown>;
  requestId: string;
}
