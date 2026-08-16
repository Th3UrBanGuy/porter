import { prisma } from "@/lib/prisma";

const CF_CLIENT_ID = process.env.CF_CLIENT_ID!;
const CF_CLIENT_SECRET = process.env.CF_CLIENT_SECRET!;

export class CloudflareClient {
  private accessToken: string;
  private refreshToken: string;
  private expiresAt: Date | null;
  private userId: string;

  constructor(
    accessToken: string,
    refreshToken: string | null,
    expiresAt: Date | null,
    userId: string
  ) {
    this.accessToken = accessToken;
    this.refreshToken = refreshToken || "";
    this.expiresAt = expiresAt;
    this.userId = userId;
  }

  static async fromUserId(userId: string): Promise<CloudflareClient | null> {
    const mcp = await prisma.mcpConnection.findUnique({
      where: { userId },
    });

    if (!mcp || !mcp.accessToken) {
      return null;
    }

    // Check if token needs refresh
    if (mcp.expiresAt && mcp.expiresAt < new Date()) {
      const refreshed = await refreshAccessToken(mcp.refreshToken!);
      if (refreshed) {
        await prisma.mcpConnection.update({
          where: { userId },
          data: {
            accessToken: refreshed.access_token,
            expiresAt: new Date(Date.now() + refreshed.expires_in * 1000),
          },
        });
        return new CloudflareClient(
          refreshed.access_token,
          mcp.refreshToken,
          new Date(Date.now() + refreshed.expires_in * 1000),
          userId
        );
      }
    }

    return new CloudflareClient(
      mcp.accessToken,
      mcp.refreshToken,
      mcp.expiresAt,
      userId
    );
  }

  private async request(path: string, options: RequestInit = {}): Promise<any> {
    const res = await fetch(`https://api.cloudflare.com/client/v4${path}`, {
      ...options,
      headers: {
        Authorization: `Bearer ${this.accessToken}`,
        "Content-Type": "application/json",
        ...options.headers,
      },
    });

    const data = await res.json();

    if (!data.success) {
      throw new Error(
        `Cloudflare API error: ${data.errors?.map((e: any) => e.message).join(", ")}`
      );
    }

    return data.result;
  }

  async listZones(): Promise<any[]> {
    return this.request("/zones");
  }

  async getZone(zoneId: string): Promise<any> {
    return this.request(`/zones/${zoneId}`);
  }

  async listTunnels(accountId: string): Promise<any[]> {
    return this.request(`/accounts/${accountId}/cfd_tunnel`);
  }

  async createTunnel(
    accountId: string,
    name: string,
    secret: string
  ): Promise<any> {
    return this.request(`/accounts/${accountId}/cfd_tunnel`, {
      method: "POST",
      body: JSON.stringify({
        name,
        tunnel_secret: secret,
      }),
    });
  }

  async deleteTunnel(accountId: string, tunnelId: string): Promise<void> {
    await this.request(`/accounts/${accountId}/cfd_tunnel/${tunnelId}`, {
      method: "DELETE",
    });
  }

  async createDNSRecord(
    zoneId: string,
    type: string,
    name: string,
    content: string,
    proxied: boolean = true
  ): Promise<any> {
    return this.request(`/zones/${zoneId}/dns_records`, {
      method: "POST",
      body: JSON.stringify({ type, name, content, proxied }),
    });
  }

  async deleteDNSRecord(zoneId: string, recordId: string): Promise<void> {
    await this.request(`/zones/${zoneId}/dns_records/${recordId}`, {
      method: "DELETE",
    });
  }

  async getAccountId(): Promise<string> {
    const accounts = await this.request("/accounts");
    return accounts[0]?.id || "";
  }
}

async function refreshAccessToken(
  refreshToken: string
): Promise<{ access_token: string; expires_in: number } | null> {
  try {
    const res = await fetch("https://dash.cloudflare.com/oauth2/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "refresh_token",
        refresh_token: refreshToken,
        client_id: CF_CLIENT_ID,
        client_secret: CF_CLIENT_SECRET,
      }),
    });

    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}
