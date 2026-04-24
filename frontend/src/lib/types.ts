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
  | "expired"
  | "trialing";

export type WebhookStatus = "pending" | "delivered" | "failed" | "dead_lettered";

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
  | "subscription.payment_confirmed"
  | "subscription.updated"
  | "subscription.paused"
  | "subscription.resumed"
  | "subscription.expired"
  | "subscription.trial_started"
  | "subscription.trial_ended";

export type NetworkMode = "live" | "test";

// === Cursor Pagination (Phase 6B) ===

export interface CursorResponse<T> {
  data: T[];
  has_more: boolean;
}

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
  description: string | null;
  amount_atomic: string;
  amount_xmr: string;
  fiat_amount: string | null;
  fiat_currency: string | null;
  fiat_rate: string | null;
  status: InvoiceStatus;
  address: string | null;
  address_index: number | null;
  expires_at: string;
  paid_at: string | null;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown> | null;
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

export interface PendingChanges {
  amount_xmr: string | null;
  amount_atomic: number | null;
  interval_days: number | null;
  grace_days_soft: number | null;
  grace_days_hard: number | null;
}

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
  billing_anchor_at: string | null;
  next_due_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown> | null;
  pending_changes: PendingChanges | null;
  has_pending_changes: boolean;
  trial_days: number | null;
  trial_end_at: string | null;
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

// === Renewal Event (Phase 6C) ===

export interface RenewalEvent {
  id: string;
  subscription_id: string;
  result: string;
  invoice_id: string | null;
  error_message: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

// === Webhook ===

export interface WebhookDelivery {
  id: string;
  invoice_id: string;
  event_type: string;
  url: string;
  payload: Record<string, unknown>;
  status: WebhookStatus;
  attempts: number;
  max_attempts: number;
  response_code: number | null;
  response_body: string | null;
  next_retry_at: string | null;
  created_at: string;
}

// === Webhook Dead Letter (Phase 6B) ===

export interface WebhookDeadLetter {
  id: string;
  delivery_id: string;
  merchant_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  original_created_at: string;
  dead_lettered_at: string;
  retry_count: number;
  last_retry_at: string | null;
  last_error: string | null;
  resolved: boolean;
  resolved_at: string | null;
}

// === API Key ===

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

// === Price ===

export interface Price {
  usd: number;
  eur: number;
  timestamp: string;
  source: string;
  stale: boolean;
}
