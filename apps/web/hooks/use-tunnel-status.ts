"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@clerk/nextjs";

interface Tunnel {
  id: string;
  subdomain: string;
  domain: string;
  port: number;
  status: string;
  url: string | null;
  connector: { name: string; status: string };
  createdAt: string;
}

export function useTunnelStatus() {
  const { getToken } = useAuth();
  const [tunnels, setTunnels] = useState<Tunnel[]>([]);

  const fetchTunnels = useCallback(async () => {
    try {
      const res = await fetch("/api/tunnels");
      const data = await res.json();
      setTunnels(data.tunnels || []);
    } catch (err) {
      console.error("Failed to fetch tunnels:", err);
    }
  }, []);

  useEffect(() => {
    fetchTunnels();

    // Subscribe to SSE for real-time updates
    const eventSource = new EventSource("/api/tunnels/events");

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.tunnels) {
          setTunnels(data.tunnels);
        }
      } catch (err) {
        console.error("SSE parse error:", err);
      }
    };

    eventSource.onerror = () => {
      // Reconnect after 5 seconds
      setTimeout(() => {
        eventSource.close();
      }, 5000);
    };

    return () => {
      eventSource.close();
    };
  }, [fetchTunnels]);

  return { tunnels, refresh: fetchTunnels };
}
