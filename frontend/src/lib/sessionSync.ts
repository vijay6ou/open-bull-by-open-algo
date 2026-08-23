/**
 * Cross-tab session sync.
 *
 * Logout and broker disconnect must apply in every OpenBull tab in this
 * browser. BroadcastChannel is the primary path; localStorage is the
 * fallback for browsers that deliver storage events across tabs only.
 */

import type { QueryClient } from "@tanstack/react-query";
import type { UserInfo } from "@/types/auth";
import type { BrokerConnectionStatus } from "@/types/broker";

export type SessionSyncEvent =
  | { type: "logout" }
  | { type: "broker-disconnected" }
  | { type: "broker-connected" };

const CHANNEL = "openbull-session";
const STORAGE_KEY = "openbull-session-sync";

let channel: BroadcastChannel | null = null;

function getChannel(): BroadcastChannel | null {
  if (typeof window === "undefined" || typeof BroadcastChannel === "undefined") {
    return null;
  }
  if (!channel) {
    channel = new BroadcastChannel(CHANNEL);
  }
  return channel;
}

export function broadcastSession(event: SessionSyncEvent): void {
  getChannel()?.postMessage(event);
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ...event, ts: Date.now() }),
    );
  } catch {
    /* quota / private mode */
  }
}

export function subscribeSession(
  handler: (event: SessionSyncEvent) => void,
): () => void {
  const ch = getChannel();
  const onMessage = (ev: MessageEvent<SessionSyncEvent>) => {
    if (ev?.data?.type) handler(ev.data);
  };
  ch?.addEventListener("message", onMessage);

  const onStorage = (ev: StorageEvent) => {
    if (ev.key !== STORAGE_KEY || !ev.newValue) return;
    try {
      const parsed = JSON.parse(ev.newValue) as SessionSyncEvent & { ts?: number };
      if (parsed?.type) handler(parsed);
    } catch {
      /* ignore */
    }
  };
  window.addEventListener("storage", onStorage);

  return () => {
    ch?.removeEventListener("message", onMessage);
    window.removeEventListener("storage", onStorage);
  };
}

export const DISCONNECTED_STATUS: BrokerConnectionStatus = {
  connected: false,
  token_valid: false,
  broker: null,
  display_name: "",
  client_id: null,
  user_id: null,
  trading_client_id: null,
  latency_ms: null,
  error_code: "disconnected",
  http_status: null,
  message:
    "Disconnected here. Session was not renewed, so other apps can keep using the keys.",
  checked_at: "",
};

export function applyBrokerDisconnected(
  queryClient: QueryClient,
  status?: Partial<BrokerConnectionStatus>,
): void {
  queryClient.setQueryData(["auth", "me"], (old: UserInfo | undefined) =>
    old ? { ...old, broker_authenticated: false } : old,
  );
  queryClient.setQueryData(["broker-status"], {
    ...DISCONNECTED_STATUS,
    ...status,
    connected: false,
    checked_at: status?.checked_at || new Date().toISOString(),
  });
  queryClient.removeQueries({ queryKey: ["dashboard"] });
  queryClient.removeQueries({ queryKey: ["positions"] });
  queryClient.removeQueries({ queryKey: ["orderbook"] });
  queryClient.removeQueries({ queryKey: ["tradebook"] });
  queryClient.removeQueries({ queryKey: ["holdings"] });
}

export function applyBrokerConnected(
  queryClient: QueryClient,
  status?: Partial<BrokerConnectionStatus>,
): void {
  queryClient.setQueryData(["auth", "me"], (old: UserInfo | undefined) =>
    old
      ? { ...old, broker_authenticated: true, broker: old.broker || "jainamxts" }
      : old,
  );
  queryClient.setQueryData(["broker-status"], {
    connected: true,
    token_valid: true,
    broker: status?.broker || "jainamxts",
    display_name: status?.display_name || "Jainam DMA",
    client_id: status?.client_id ?? null,
    user_id: status?.user_id ?? null,
    trading_client_id: status?.trading_client_id ?? null,
    latency_ms: status?.latency_ms ?? null,
    error_code: null,
    http_status: 200,
    message: status?.message || "Connected",
    checked_at: new Date().toISOString(),
  });
}

export function goToLogin(): void {
  if (window.location.pathname !== "/login") {
    window.location.replace("/login");
  }
}

export const STAY_ON_LOGIN_KEY = "openbull-stay-on-login";

export function markStayOnLogin(): void {
  try {
    sessionStorage.setItem(STAY_ON_LOGIN_KEY, "1");
  } catch {
    /* ignore */
  }
}

export function clearStayOnLogin(): void {
  try {
    sessionStorage.removeItem(STAY_ON_LOGIN_KEY);
  } catch {
    /* ignore */
  }
}

export function shouldStayOnLogin(): boolean {
  try {
    return sessionStorage.getItem(STAY_ON_LOGIN_KEY) === "1";
  } catch {
    return false;
  }
}
