// === Enums ===

export type InvoiceStatus =
  | "pending"
  | "paid"
  | "expired"
  | "partially_paid"
  | "overpaid"
  | "late_paid"
  | "cancelled";

export type PaymentStatus = "detected" | "confirmed" | "orphaned";

export type SubscriptionStatus =
  | "active"
  | "paused"
  | "past_due"
  | "cancelled"
  | "expired";

export type WebhookEvent =
  | "payment.detected"
  | "payment.confirmed"
  | "payment.orphaned"
  | "invoice.paid"
  | "invoice.expired"
  | "invoice.partially_paid"
  | "invoice.overpaid"
  | "invoice.late_paid"
  | "subscription.created"
  | "subscription.renewed"
  | "subscription.past_due"
  | "subscription.cancelled"
  | "subscription.payment_confirmed";

export type NetworkMode = "live" | "test";

// === Merchant ===

export interface Merchant {
  id: string;
  name: string;
  email: string;
  webhook_url: string | null;
  webhook_secret: string | null;
  created_at: string;
  updated_at: string;
}

// === Customer ===

export interface Customer {
  id: string;
  merchant_id: string;
  external_id: string | null;
  email: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

// === Invoice ===

export interface Invoice {
  id: string;
  merchant_id: string;
  external_id: string | null;
  description: string | null;
  amount_atomic: string;
  amount_xmr: string;
  fiat_amount: string | null;
  fiat_currency: string | null;
  status: InvoiceStatus;
  subaddress: string;
  subaddress_index: number;
  paid_atomic: string;
  confirmations_required: number;
  expires_at: string;
  created_at: string;
  updated_at: string;
  payments: Payment[];
}

// === Payment ===

export interface Payment {
  id: string;
  invoice_id: string;
  tx_hash: string;
  amount_atomic: string;
  amount_xmr: string;
  confirmations: number;
  status: PaymentStatus;
  detected_at: string;
  confirmed_at: string | null;
  block_height: number | null;
}

// === Subscription ===

export interface Subscription {
  id: string;
  merchant_id: string;
  customer_id: string;
  status: SubscriptionStatus;
  amount_xmr: string;
  amount_atomic: string;
  interval_days: number;
  grace_days_soft: number;
  grace_days_hard: number;
  next_due_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  metadata: Record<string, unknown>;
  customer?: CustomerSummary;
  payments?: SubscriptionPaymentInfo[];
}

export interface CustomerSummary {
  id: string;
  external_id: string | null;
  email: string | null;
}

export interface SubscriptionPaymentInfo {
  id: string;
  period_start: string;
  period_end: string;
  invoice_id: string;
  invoice_status: InvoiceStatus;
  paid_at: string | null;
}

// === Webhook ===

export interface WebhookDelivery {
  id: string;
  invoice_id: string;
  event: WebhookEvent;
  url: string;
  payload: Record<string, unknown>;
  response_status: number | null;
  response_body: string | null;
  attempt: number;
  max_attempts: number;
  next_retry_at: string | null;
  delivered_at: string | null;
  created_at: string;
}

// === API Key (matches backend ApiKeyResponse) ===

export interface ApiKey {
  id: string;
  key_prefix: string;
  label: string | null;
  environment: NetworkMode;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string | null;
}

export interface ApiKeyCreated {
  id: string;
  key: string;
  key_prefix: string;
  label: string | null;
  environment: NetworkMode;
}

// === Price (matches GET /v1/price response) ===

export interface Price {
  usd: number;
  eur: number;
  timestamp: string;
  source: string;
  stale: boolean;
}

// === Pagination (matches API responses) ===

export interface InvoiceListResponse {
  invoices: Invoice[];
  total: number;
  limit: number;
  offset: number;
}

export interface PaymentListResponse {
  payments: Payment[];
  total: number;
  limit: number;
  offset: number;
}

export interface CustomerListResponse {
  customers: Customer[];
  total: number;
  limit: number;
  offset: number;
}

export interface SubscriptionListResponse {
  subscriptions: Subscription[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApiKeyListResponse {
  api_keys: ApiKey[];
  total: number;
}

export interface WebhookDeliveryListResponse {
  deliveries: WebhookDelivery[];
  total: number;
  limit: number;
  offset: number;
}
