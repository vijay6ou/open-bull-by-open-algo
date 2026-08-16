import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getBrokerStatus, jainamxtsLogin } from "@/api/broker";
import { cn } from "@/lib/utils";

export function useBrokerStatus() {
  return useQuery({
    queryKey: ["broker-status"],
    queryFn: getBrokerStatus,
    refetchInterval: 5000,
    refetchOnWindowFocus: true,
    staleTime: 2000,
  });
}

async function reconnectBroker(broker: string | null) {
  if (broker === "jainamxts") {
    await jainamxtsLogin();
    return;
  }
  throw new Error("select");
}

export function BrokerConnectionStatus() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data, isLoading, isFetching } = useBrokerStatus();
  const [busy, setBusy] = useState(false);
  const wasConnected = useRef<boolean | null>(null);

  useEffect(() => {
    if (data?.connected && wasConnected.current === false) {
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["positions"] });
      queryClient.invalidateQueries({ queryKey: ["orderbook"] });
      queryClient.invalidateQueries({ queryKey: ["tradebook"] });
      queryClient.invalidateQueries({ queryKey: ["holdings"] });
    }
    if (data) wasConnected.current = data.connected;
  }, [data, data?.connected, queryClient]);

  const connected = data?.connected === true;
  const label = data?.display_name || data?.broker || "Broker";
  const latency =
    connected && data?.latency_ms != null ? `${data.latency_ms}ms` : null;

  const handleReconnect = async () => {
    setBusy(true);
    try {
      await reconnectBroker(data?.broker ?? "jainamxts");
      await queryClient.invalidateQueries();
    } catch {
      navigate("/broker/select");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="flex items-center gap-2"
      title={
        connected
          ? `${label} live${data?.client_id ? ` · ${data.client_id}` : ""}${latency ? ` · ${latency}` : ""}`
          : data?.message || "Broker disconnected"
      }
      role="status"
      aria-live="polite"
    >
      <span
        className={cn(
          "inline-block h-2.5 w-2.5 rounded-full",
          isLoading
            ? "bg-amber-400 animate-pulse"
            : connected
              ? "bg-emerald-500"
              : "bg-rose-500",
          connected && isFetching && "animate-pulse"
        )}
      />
      <span className="hidden text-xs font-medium tracking-tight sm:inline">
        {isLoading ? (
          <span className="text-muted-foreground">Checking broker…</span>
        ) : connected ? (
          <span className="text-foreground">
            Connected
            {latency && (
              <span className="ml-1 font-normal text-muted-foreground tabular-nums">
                {latency}
              </span>
            )}
          </span>
        ) : (
          <button
            type="button"
            onClick={handleReconnect}
            disabled={busy}
            className="text-rose-600 hover:underline dark:text-rose-400"
          >
            {busy ? "Reconnecting…" : "Disconnected"}
          </button>
        )}
      </span>
    </div>
  );
}

export function BrokerDisconnectedBanner() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data, isLoading } = useBrokerStatus();
  const [busy, setBusy] = useState(false);

  if (isLoading || data?.connected) return null;

  const label = data?.display_name || data?.broker || "Broker";
  const detail = data?.message && data.message !== "Not connected" ? data.message : null;

  const handleReconnect = async () => {
    setBusy(true);
    try {
      await reconnectBroker(data?.broker ?? "jainamxts");
      await queryClient.invalidateQueries();
    } catch {
      navigate("/broker/select");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 border-b border-rose-800 bg-rose-600 px-4 py-2 text-[12px] font-semibold tracking-wide text-white shadow-sm"
      role="status"
      aria-live="assertive"
    >
      <span
        className="inline-block h-2 w-2 rounded-full bg-white ring-2 ring-white/40"
        aria-hidden
      />
      <span className="uppercase tracking-[0.14em]">Disconnected</span>
      <span className="text-white/70" aria-hidden>
        ·
      </span>
      <span className="font-medium normal-case tracking-normal text-white/90">
        {label} is not live{detail ? ` — ${detail}` : ""}
      </span>
      <button
        type="button"
        onClick={handleReconnect}
        disabled={busy}
        className="rounded bg-white/15 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.12em] hover:bg-white/25 disabled:opacity-70"
      >
        {busy ? "Reconnecting…" : "Reconnect"}
      </button>
    </div>
  );
}
