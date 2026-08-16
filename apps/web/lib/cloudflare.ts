/**
 * Cloudflare MCP client (same approach as v1).
 * Uses OAuth 2.1 with PKCE via mcp.cloudflare.com.
 * All Cloudflare API calls go through MCP's execute tool.
 */

import crypto from "crypto";
import { prisma } from "./prisma";

const CF_MCP_BASE = "https://mcp.cloudflare.com";
const CF_MCP_URL = `${CF_MCP_BASE}/mcp`;

function b64url(data: Buffer): string {
  return data.toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function pkceChallenge(verifier: string): string {
  const digest = crypto.createHash("sha256").update(verifier).digest();
  return b64url(digest);
}

interface OAuthMetadata {
  authorization_endpoint: string;
  token_endpoint: string;
  registration_endpoint: string;
}

interface ClientInfo {
  client_id: string;
  client_secret?: string;
}

interface TokenData {
  access_token: string;
  refresh_token?: string;
  expires_in: number;
  expires_at?: number;
}

export class CloudflareMCPClient {
  private metadata: OAuthMetadata | null = null;
  private clientInfo: ClientInfo | null = null;
  private requestId = 0;

  private async discoverMetadata(): Promise<OAuthMetadata> {
    if (this.metadata) return this.metadata;

    try {
      const res = await fetch(`${CF_MCP_BASE}/.well-known/oauth-authorization-server`);
      if (res.ok) {
        this.metadata = await res.json();
        return this.metadata!;
      }
    } catch {}

    this.metadata = {
      authorization_endpoint: `${CF_MCP_BASE}/authorize`,
      token_endpoint: `${CF_MCP_BASE}/token`,
      registration_endpoint: `${CF_MCP_BASE}/register`,
    };
    return this.metadata;
  }

  private async registerClient(): Promise<ClientInfo> {
    const metadata = await this.discoverMetadata();

    const res = await fetch(metadata.registration_endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_name: "Porter v2",
        redirect_uris: [process.env.CF_REDIRECT_URI || "http://localhost:3000/api/auth/cloudflare/callback"],
        grant_types: ["authorization_code", "refresh_token"],
        response_types: ["code"],
        token_endpoint_auth_method: "none",
      }),
    });

    if (!res.ok) throw new Error(`Client registration failed: ${res.status}`);
    this.clientInfo = await res.json();
    return this.clientInfo!;
  }

  async generateAuthUrl(): Promise<{ url: string; state: string; codeVerifier: string }> {
    await this.discoverMetadata();
    const clientInfo = await this.registerClient();

    const codeVerifier = b64url(crypto.randomBytes(32));
    const codeChallenge = pkceChallenge(codeVerifier);
    const state = crypto.randomBytes(16).toString("hex");

    const params = new URLSearchParams({
      response_type: "code",
      client_id: clientInfo.client_id,
      redirect_uri: process.env.CF_REDIRECT_URI || "http://localhost:3000/api/auth/cloudflare/callback",
      state,
      code_challenge: codeChallenge,
      code_challenge_method: "S256",
    });

    return {
      url: `${this.metadata!.authorization_endpoint}?${params.toString()}`,
      state,
      codeVerifier,
    };
  }

  async exchangeCode(
    code: string,
    state: string,
    storedState: string,
    codeVerifier: string,
    clientInfo: ClientInfo
  ): Promise<TokenData> {
    if (state !== storedState) throw new Error("State mismatch");

    const metadata = await this.discoverMetadata();

    const res = await fetch(metadata.token_endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        code,
        redirect_uri: process.env.CF_REDIRECT_URI || "http://localhost:3000/api/auth/cloudflare/callback",
        client_id: clientInfo.client_id,
        code_verifier: codeVerifier,
      }),
    });

    if (!res.ok) throw new Error(`Token exchange failed: ${res.status}`);
    const data = await res.json();
    data.expires_at = Date.now() + data.expires_in * 1000;
    return data;
  }

  async refreshAccessToken(
    refreshToken: string,
    clientInfo: ClientInfo
  ): Promise<TokenData | null> {
    try {
      const metadata = await this.discoverMetadata();

      const res = await fetch(metadata.token_endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          grant_type: "refresh_token",
          refresh_token: refreshToken,
          client_id: clientInfo.client_id,
        }),
      });

      if (!res.ok) return null;
      const data = await res.json();
      data.expires_at = Date.now() + data.expires_in * 1000;
      if (!data.refresh_token) data.refresh_token = refreshToken;
      return data;
    } catch {
      return null;
    }
  }

  async getValidToken(userId: string): Promise<string | null> {
    const mcp = await prisma.mcpConnection.findUnique({ where: { userId } });
    if (!mcp || !mcp.accessToken) return null;

    // Check if token needs refresh
    if (mcp.expiresAt && mcp.expiresAt.getTime() > Date.now() + 60000) {
      return mcp.accessToken;
    }

    // Try refresh
    if (mcp.refreshToken && mcp.clientInfo) {
      const clientInfo = mcp.clientInfo as unknown as ClientInfo;
      const refreshed = await this.refreshAccessToken(mcp.refreshToken, clientInfo);
      if (refreshed) {
        await prisma.mcpConnection.update({
          where: { userId },
          data: {
            accessToken: refreshed.access_token,
            expiresAt: new Date(refreshed.expires_at!),
          },
        });
        return refreshed.access_token;
      }
    }

    return null;
  }

  async mcpCall(userId: string, toolName: string, args: any): Promise<any> {
    const token = await this.getValidToken(userId);
    if (!token) throw new Error("Not authenticated with Cloudflare");

    const payload = {
      jsonrpc: "2.0",
      id: ++this.requestId,
      method: "tools/call",
      params: { name: toolName, arguments: args },
    };

    let res = await fetch(CF_MCP_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        Accept: "application/json, text/event-stream",
      },
      body: JSON.stringify(payload),
    });

    // Auto-retry on 401
    if (res.status === 401) {
      const mcp = await prisma.mcpConnection.findUnique({ where: { userId } });
      if (mcp?.refreshToken && mcp.clientInfo) {
        const clientInfo = mcp.clientInfo as unknown as ClientInfo;
        const refreshed = await this.refreshAccessToken(mcp.refreshToken, clientInfo);
        if (refreshed) {
          await prisma.mcpConnection.update({
            where: { userId },
            data: {
              accessToken: refreshed.access_token,
              expiresAt: new Date(refreshed.expires_at!),
            },
          });
          res = await fetch(CF_MCP_URL, {
            method: "POST",
            headers: {
              Authorization: `Bearer ${refreshed.access_token}`,
              "Content-Type": "application/json",
              Accept: "application/json, text/event-stream",
            },
            body: JSON.stringify(payload),
          });
        }
      }
    }

    const contentType = res.headers.get("content-type") || "";
    const text = await res.text();

    if (contentType.includes("text/event-stream")) {
      return this.parseSSEResponse(text);
    }

    if (res.ok) {
      const data = JSON.parse(text);
      if (data.result) return this.extractResult(data.result);
      if (data.error) throw new Error(`MCP error: ${JSON.stringify(data.error)}`);
    }

    throw new Error(`MCP call failed: ${res.status} ${text.slice(0, 500)}`);
  }

  private parseSSEResponse(text: string): any {
    for (const line of text.split("\n")) {
      if (line.startsWith("data: ")) {
        try {
          const data = JSON.parse(line.slice(6).trim());
          if (data.result) return this.extractResult(data.result);
          if (data.error) throw new Error(`MCP error: ${JSON.stringify(data.error)}`);
        } catch {}
      }
    }
    throw new Error("No valid response in SSE stream");
  }

  private extractResult(result: any): any {
    if (typeof result === "object" && result?.content) {
      const texts = result.content
        .filter((c: any) => c.type === "text")
        .map((c: any) => c.text);
      const fullText = texts.join("\n");
      try {
        return JSON.parse(fullText);
      } catch {
        return fullText;
      }
    }
    return result;
  }

  async executeCode(userId: string, code: string): Promise<any> {
    const result = await this.mcpCall(userId, "execute", { code });
    if (typeof result === "string" && result.startsWith("Error:")) {
      throw new Error(result);
    }
    return result;
  }

  // === High-level API methods ===

  async getAccountId(userId: string): Promise<string> {
    const code = `
async () => {
  const response = await cloudflare.request({
    method: "GET",
    path: "/accounts?per_page=1"
  });
  return response.result;
}`;
    const result = await this.executeCode(userId, code);
    if (Array.isArray(result) && result.length > 0) return result[0].id;
    if (result?.id) return result.id;
    throw new Error("No Cloudflare account found");
  }

  async getZoneId(userId: string, domain: string): Promise<string> {
    const code = `
async () => {
  const response = await cloudflare.request({
    method: "GET",
    path: "/zones?name=${domain}"
  });
  return response.result;
}`;
    const result = await this.executeCode(userId, code);
    if (Array.isArray(result) && result.length > 0) return result[0].id;
    if (result?.id) return result.id;
    throw new Error(`Zone not found for ${domain}`);
  }

  async listZones(userId: string): Promise<any[]> {
    const code = `
async () => {
  const response = await cloudflare.request({
    method: "GET",
    path: "/zones?per_page=50"
  });
  return response.result;
}`;
    const result = await this.executeCode(userId, code);
    return Array.isArray(result) ? result : [];
  }

  async createDNSRecord(
    userId: string,
    zoneId: string,
    type: string,
    name: string,
    content: string,
    proxied = true
  ): Promise<any> {
    const body = JSON.stringify({ type, name, content, proxied });
    const code = `
async () => {
  const response = await cloudflare.request({
    method: "POST",
    path: "/zones/${zoneId}/dns_records",
    body: ${body}
  });
  return response.result;
}`;
    const result = await this.executeCode(userId, code);
    if (result?.id) return result;
    throw new Error(`DNS create failed: ${result}`);
  }

  async deleteDNSRecord(userId: string, zoneId: string, recordId: string): Promise<void> {
    const code = `
async () => {
  const response = await cloudflare.request({
    method: "DELETE",
    path: "/zones/${zoneId}/dns_records/${recordId}"
  });
  return response;
}`;
    await this.executeCode(userId, code);
  }

  async listDNSRecords(userId: string, zoneId: string): Promise<any[]> {
    const code = `
async () => {
  const response = await cloudflare.request({
    method: "GET",
    path: "/zones/${zoneId}/dns_records?per_page=100"
  });
  return response.result;
}`;
    const result = await this.executeCode(userId, code);
    return Array.isArray(result) ? result : [];
  }

  async createTunnel(userId: string, name: string): Promise<any> {
    const accountId = await this.getAccountId(userId);
    const secret = b64url(crypto.randomBytes(32));
    const code = `
async () => {
  const response = await cloudflare.request({
    method: "POST",
    path: "/accounts/${accountId}/cfd_tunnel",
    body: {
      name: "${name}",
      tunnel_secret: "${secret}"
    }
  });
  return response.result;
}`;
    const result = await this.executeCode(userId, code);
    if (result?.id) return result;
    throw new Error(`Tunnel create failed: ${result}`);
  }

  async getTunnelToken(userId: string, tunnelId: string): Promise<string> {
    const accountId = await this.getAccountId(userId);
    const code = `
async () => {
  const response = await cloudflare.request({
    method: "GET",
    path: "/accounts/${accountId}/cfd_tunnel/${tunnelId}/token"
  });
  return response.result;
}`;
    const result = await this.executeCode(userId, code);
    return typeof result === "string" ? result : result?.token || "";
  }

  async addTunnelHostname(
    userId: string,
    tunnelId: string,
    hostname: string,
    service: string
  ): Promise<void> {
    const accountId = await this.getAccountId(userId);

    // Get existing config
    const getCode = `
async () => {
  const response = await cloudflare.request({
    method: "GET",
    path: "/accounts/${accountId}/cfd_tunnel/${tunnelId}/configurations"
  });
  return response.result;
}`;
    const existing = await this.executeCode(userId, getCode);
    const existingIngress = existing?.config?.ingress || [];

    const hostnameRules = existingIngress.filter((r: any) => r.hostname);
    const catchAll = existingIngress.filter((r: any) => r.service === "http_status:404");

    hostnameRules.push({ hostname, service, originRequest: {} });
    const ingress = hostnameRules.concat(
      catchAll.length > 0 ? catchAll : [{ service: "http_status:404" }]
    );

    const body = JSON.stringify({ config: { ingress } });
    const putCode = `
async () => {
  const response = await cloudflare.request({
    method: "PUT",
    path: "/accounts/${accountId}/cfd_tunnel/${tunnelId}/configurations",
    body: ${body}
  });
  return response;
}`;
    await this.executeCode(userId, putCode);
  }

  async removeTunnelHostname(
    userId: string,
    tunnelId: string,
    hostname: string
  ): Promise<void> {
    const accountId = await this.getAccountId(userId);

    const getCode = `
async () => {
  const response = await cloudflare.request({
    method: "GET",
    path: "/accounts/${accountId}/cfd_tunnel/${tunnelId}/configurations"
  });
  return response.result;
}`;
    const existing = await this.executeCode(userId, getCode);
    if (!existing?.config) return;

    const ingress = existing.config.ingress || [];
    const filtered = ingress.filter((r: any) => r.hostname !== hostname);
    if (filtered.length === ingress.length) return;

    if (!filtered.some((r: any) => r.service === "http_status:404")) {
      filtered.push({ service: "http_status:404" });
    }

    const body = JSON.stringify({ config: { ingress: filtered } });
    const putCode = `
async () => {
  const response = await cloudflare.request({
    method: "PUT",
    path: "/accounts/${accountId}/cfd_tunnel/${tunnelId}/configurations",
    body: ${body}
  });
  return response;
}`;
    await this.executeCode(userId, putCode);
  }

  async listTunnels(userId: string): Promise<any[]> {
    const accountId = await this.getAccountId(userId);
    const code = `
async () => {
  const response = await cloudflare.request({
    method: "GET",
    path: "/accounts/${accountId}/cfd_tunnel?per_page=50"
  });
  return response.result;
}`;
    const result = await this.executeCode(userId, code);
    return Array.isArray(result) ? result : [];
  }

  async deleteTunnel(userId: string, tunnelId: string): Promise<void> {
    const accountId = await this.getAccountId(userId);
    const code = `
async () => {
  const response = await cloudflare.request({
    method: "DELETE",
    path: "/accounts/${accountId}/cfd_tunnel/${tunnelId}"
  });
  return response;
}`;
    await this.executeCode(userId, code);
  }
}

export const cfMCP = new CloudflareMCPClient();
