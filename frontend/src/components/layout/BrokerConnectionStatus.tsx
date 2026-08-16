import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  disconnectBroker,
  getBrokerStatus,
  jainamxtsLogin,
} from "@/api/broker";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import {
  applyBrokerDisconnected,
  broadcastSession,
} from "@/lib/sessionSync";
import type { BrokerConnectionStatus } from "@/types/broker";

function loginErrorMessage(err: unknown): string {
  const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
  const detail = axiosErr.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  return axiosErr.message || "Broker login failed";
}

const CONNECT_WARNING =
  "This logs in to Jainam DMA with the stored keys and can disconnect any other app that is already using the same session. OpenBull will not reconnect by itself after that.";

export function useBrokerStatus() {
  const query = useQuery({
    queryKey: ["broker-status"],
    queryFn: getBrokerStatus,
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 10_000,
    // Heartbeat only while connected. A failed ping must not retry forever.
    refetchInterval: (q) => (q.state.data?.connected ? 15_000 : false),
  });
  const wasConnected = useRef<boolean | null>(null);
  useEffect(() => {
    const connected = query.data?.connected === true;
    if (wasConnected.current === true && !connected) {
      broadcastSession({ type: "broker-disconnected" });
    }
    if (query.data) wasConnected.current = connected;
  }, [query.data, query.data?.connected]);
  return query;
}

function formatBrokerError(data?: BrokerConnectionStatus | null): string {
  if (!data) return "No broker session";
  const bits = [data.error_code, data.message].filter(Boolean);
  if (data.http_status && data.http_status >= 400) {
    bits.unshift(`HTTP ${data.http_status}`);
  }
  return bits.join(" · ") || "Disconnected";
}

export function BrokerConnectionStatus() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useBrokerStatus();
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<"connect" | "disconnect" | null>(null);

  const connected = data?.connected === true;

  const runDisconnect = async () => {
    setBusy(true);
    try {
      const status = await disconnectBroker();
      applyBrokerDisconnected(queryClient, status);
      broadcastSession({ type: "broker-disconnected" });
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  };

  const runConnect = async () => {
    setBusy(true);
    try {
      await jainamxtsLogin();
      broadcastSession({ type: "broker-connected" });
      await queryClient.invalidateQueries({ queryKey: ["broker-status"] });
      await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
    } catch (err) {
      toast.error(loginErrorMessage(err));
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  };

  return (
    <>
      <div
        className="flex items-center gap-2"
        title={
          connected
            ? `${data?.display_name || "Broker"} live${data?.client_id ? ` · ${data.client_id}` : ""}`
            : formatBrokerError(data)
        }
        role="status"
        aria-live="polite"
      >
        <span
          className={cn(
            "inline-block h-2.5 w-2.5 rounded-full",
            isLoading
              ? "bg-amber-400"
              : connected
                ? "bg-emerald-500"
                : "bg-rose-500",
          )}
        />
        <span className="hidden max-w-[220px] truncate text-xs font-medium tracking-tight sm:inline">
          {isLoading ? (
            <span className="text-muted-foreground">Checking…</span>
          ) : connected ? (
            <span className="text-foreground">
              Connected
              {data?.latency_ms != null && (
                <span className="ml-1 font-normal text-muted-foreground tabular-nums">
                  {data.latency_ms}ms
                </span>
              )}
            </span>
          ) : (
            <span className="text-rose-600 dark:text-rose-400">
              {data?.error_code || "Disconnected"}
            </span>
          )}
        </span>
        {connected ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => setConfirm("disconnect")}
            className="hidden text-[11px] font-medium text-muted-foreground hover:text-foreground sm:inline"
          >
            Disconnect
          </button>
        ) : (
          !isLoading && (
            <button
              type="button"
              disabled={busy}
              onClick={() => setConfirm("connect")}
              className="hidden text-[11px] font-medium text-muted-foreground hover:text-foreground sm:inline"
            >
              Connect
            </button>
          )
        )}
      </div>

      <ConfirmDialog
        open={confirm === "connect"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title="Connect Jainam DMA?"
        description={CONNECT_WARNING}
        confirmLabel="Connect"
        loading={busy}
        onConfirm={runConnect}
      />
      <ConfirmDialog
        open={confirm === "disconnect"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title="Disconnect this app?"
        description="OpenBull will drop its broker session and will not reconnect. Other apps using the same keys are left alone. This applies to every OpenBull tab."
        confirmLabel="Disconnect"
        variant="destructive"
        loading={busy}
        onConfirm={runDisconnect}
      />
    </>
  );
}

export function BrokerDisconnectedBanner() {
  const { data, isLoading } = useBrokerStatus();
  if (isLoading || data?.connected) return null;
  const error = formatBrokerError(data);
  return (
    <div
      className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 border-b border-rose-800 bg-rose-600 px-4 py-2 text-[12px] font-medium tracking-wide text-white shadow-sm"
      role="status"
      aria-live="polite"
    >
      <span className="uppercase tracking-[0.14em]">Disconnected</span>
      <span className="text-white/70" aria-hidden>
        ·
      </span>
      <span className="font-mono text-[11px] font-semibold normal-case tracking-normal">
        {data?.error_code || "no_session"}
      </span>
      <span className="max-w-[40rem] truncate font-normal normal-case tracking-normal text-white/90">
        {data?.message || error}
      </span>
    </div>
  );
}

export function BrokerOfflinePanel({ title }: { title?: string }) {
  const queryClient = useQueryClient();
  const { data } = useBrokerStatus();
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);

  return (
    <div className="flex items-center justify-center py-20">
      <div className="max-w-md space-y-3 rounded-md border border-rose-500/30 bg-rose-500/8 p-6 text-center">
        <p className="text-sm font-semibold tracking-tight text-foreground">
          {title || `${data?.display_name || "Broker"} is disconnected`}
        </p>
        <p className="font-mono text-[12px] font-semibold text-rose-700 dark:text-rose-400">
          {data?.error_code || "no_session"}
          {data?.http_status ? ` · HTTP ${data.http_status}` : ""}
        </p>
        <p className="text-[13px] text-muted-foreground">
          {data?.message || "No broker session"}
        </p>
        <p className="text-[11px] text-muted-foreground">
          OpenBull will not reconnect on its own. Connect only if you want
          this app to take the Symphony session.
        </p>
        <button
          type="button"
          className="inline-flex h-9 items-center rounded-md bg-foreground px-3 text-sm font-medium text-background"
          disabled={busy}
          onClick={() => setConfirm(true)}
        >
          Connect
        </button>
      </div>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Connect Jainam DMA?"
        description={CONNECT_WARNING}
        confirmLabel="Connect"
        loading={busy}
        onConfirm={async () => {
          setBusy(true);
          try {
            await jainamxtsLogin();
            broadcastSession({ type: "broker-connected" });
            await queryClient.invalidateQueries();
          } catch (err) {
            toast.error(loginErrorMessage(err));
          } finally {
            setBusy(false);
            setConfirm(false);
          }
        }}
      />
    </div>
  );
}
