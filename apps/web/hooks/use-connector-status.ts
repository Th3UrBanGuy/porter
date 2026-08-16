"use client";

import { useEffect, useState, useCallback } from "react";

interface Connector {
  id: string;
  name: string;
  status: string;
  lastSeen: string | null;
  token?: string;
}

export function useConnectorStatus() {
  const [connectors, setConnectors] = useState<Connector[]>([]);

  const fetchConnectors = useCallback(async () => {
    try {
      const res = await fetch("/api/connectors");
      const data = await res.json();
      setConnectors(data.connectors || []);
    } catch (err) {
      console.error("Failed to fetch connectors:", err);
    }
  }, []);

  useEffect(() => {
    fetchConnectors();
    const interval = setInterval(fetchConnectors, 5000);
    return () => clearInterval(interval);
  }, [fetchConnectors]);

  return { connectors, refresh: fetchConnectors };
}
