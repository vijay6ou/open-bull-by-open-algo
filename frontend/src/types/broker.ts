export interface BrokerListItem {
  name: string;
  display_name: string;
  supported_exchanges: string[];
  is_configured: boolean;
  is_active: boolean;
  oauth_type: string;
}

export interface BrokerConfigData {
  broker: string;
  api_key: string;
  api_secret: string;
  redirect_url: string;
  client_id?: string;
  api_key_market?: string;
  api_secret_market?: string;
}

export interface BrokerConfigResponse {
  status: string;
  message: string;
}

export interface BrokerRedirectResponse {
  url: string;
  kind?: "internal" | "external" | "direct";
}

export interface AngelLoginPayload {
  clientcode: string;
  broker_pin: string;
  totp_code: string;
}

export interface BrokerConnectionStatus {
  connected: boolean;
  token_valid: boolean;
  broker: string | null;
  display_name: string;
  client_id: string | null;
  user_id: string | null;
  trading_client_id: string | null;
  latency_ms: number | null;
  message: string;
  checked_at: string;
}
