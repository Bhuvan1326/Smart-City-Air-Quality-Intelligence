"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Cookies from "js-cookie";

interface WSMessage {
  type: string;
  data: unknown;
  timestamp: string;
}

export function useWebSocket(city: string) {
  const wsRef = useRef<WebSocket | null>(null);
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  // Guards against scheduling a reconnect after an intentional close
  // (component unmount / effect cleanup / navigation). Without this, the
  // socket's own onclose handler fires for BOTH unexpected drops and
  // intentional closes, so an unmount would otherwise still queue a
  // reconnect timer and open a duplicate/leaked connection later.
  const intentionalCloseRef = useRef(false);

  const connect = useCallback(() => {
    const token = Cookies.get("access_token");
    if (!token) return;

    intentionalCloseRef.current = false;

    const wsBase = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";
    const url = `${wsBase}/api/v1/ws/live/${city}?token=${token}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => {
      setIsConnected(false);
      if (intentionalCloseRef.current) {
        // Cleanup/unmount initiated this close — do not reconnect.
        return;
      }
      reconnectTimeout.current = setTimeout(connect, 5000);
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as WSMessage;
        setLastMessage(msg);
      } catch {}
    };

    const heartbeat = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send("ping");
    }, 30000);

    return () => {
      intentionalCloseRef.current = true;
      clearInterval(heartbeat);
      ws.close();
    };
  }, [city]);

  useEffect(() => {
    const cleanup = connect();
    return () => {
      intentionalCloseRef.current = true;
      clearTimeout(reconnectTimeout.current);
      cleanup?.();
    };
  }, [connect]);

  return { lastMessage, isConnected };
}
