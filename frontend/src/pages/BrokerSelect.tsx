import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { listBrokers, getBrokerRedirectUrl, jainamxtsLogin } from "@/api/broker";
import { broadcastSession } from "@/lib/sessionSync";

export default function BrokerSelect() {
  const [redirecting, setRedirecting] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [confirmDma, setConfirmDma] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: brokers, isLoading, error } = useQuery({
    queryKey: ["brokers"],
    queryFn: listBrokers,
  });

  const handleBrokerClick = async (brokerName: string) => {
    setRedirecting(brokerName);
    setErrorMessage("");
    try {
      const response = await getBrokerRedirectUrl(brokerName);
      if (response.kind === "internal") {
        navigate(response.url);
      } else if (response.kind === "direct") {
        setRedirecting(null);
        setConfirmDma(true);
      } else {
        window.location.href = response.url;
      }
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setErrorMessage(axiosErr.response?.data?.detail ?? "Broker login failed. Please try again.");
      setRedirecting(null);
    }
  };

  const connectDma = async () => {
    setRedirecting("jainamxts");
    setErrorMessage("");
    try {
      await jainamxtsLogin();
      broadcastSession({ type: "broker-connected" });
      await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
      await queryClient.invalidateQueries({ queryKey: ["broker-status"] });
      navigate("/dashboard");
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setErrorMessage(
        axiosErr.response?.data?.detail ?? "Jainam DMA login failed. Check the error and try again.",
      );
      setRedirecting(null);
    } finally {
      setConfirmDma(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-muted border-t-primary" />
          <p className="text-sm text-muted-foreground">Loading brokers...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="rounded-md bg-destructive/10 p-4 text-sm text-destructive">
          Failed to load brokers. Please try again.
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4">
      <div className="w-full max-w-3xl space-y-6">
        <div className="text-center">
          <h1 className="text-2xl font-bold tracking-tight">Select Broker</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Connecting takes the live Symphony session. If those keys are in
            use elsewhere, that other app will be disconnected.
          </p>
          <Link
            to="/dashboard"
            className="mt-2 inline-block text-xs font-medium text-muted-foreground underline-offset-2 hover:underline"
          >
            Continue without connecting
          </Link>
          {errorMessage && (
            <div className="mt-3 rounded-md bg-destructive/10 p-3 text-sm text-destructive">
              {errorMessage}
            </div>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          {brokers?.map((broker) => (
            <Card key={broker.name} className="transition-shadow hover:shadow-md">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>{broker.display_name}</CardTitle>
                  {broker.is_configured ? (
                    <Badge variant="secondary">Configured</Badge>
                  ) : (
                    <Badge variant="outline">Not Configured</Badge>
                  )}
                </div>
                <CardDescription>
                  Exchanges: {broker.supported_exchanges.join(", ")}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {broker.is_configured ? (
                  <Button
                    className="w-full"
                    onClick={() => handleBrokerClick(broker.name)}
                    disabled={redirecting === broker.name}
                  >
                    {redirecting === broker.name
                      ? broker.name === "jainamxts"
                        ? "Logging in..."
                        : "Redirecting..."
                      : "Login with " + broker.display_name}
                  </Button>
                ) : (
                  <Link to="/broker/config">
                    <Button variant="outline" className="w-full">
                      Configure
                    </Button>
                  </Link>
                )}
              </CardContent>
            </Card>
          ))}
        </div>

        {brokers?.length === 0 && (
          <div className="text-center">
            <p className="text-sm text-muted-foreground">
              No brokers available.{" "}
              <Link to="/broker/config" className="font-medium text-primary underline underline-offset-4">
                Configure a broker
              </Link>
            </p>
          </div>
        )}
      </div>
      <ConfirmDialog
        open={confirmDma}
        onOpenChange={setConfirmDma}
        title="Connect Jainam DMA?"
        description="This logs in with the stored keys and can disconnect any other app already using the same Symphony session. OpenBull will not reconnect by itself afterwards."
        confirmLabel="Connect"
        loading={redirecting === "jainamxts"}
        onConfirm={connectDma}
      />
    </div>
  );
}
