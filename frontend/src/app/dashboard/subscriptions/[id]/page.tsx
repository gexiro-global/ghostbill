"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Loader2,
  XCircle,
  Pause,
  Play,
  Ban,
  Clock,
  CheckCircle,
  AlertTriangle,
  CreditCard,
  CalendarCheck,
} from "lucide-react";
import { api } from "@/lib/api";
import { formatXMR, formatDate, timeAgo } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import CopyButton from "@/components/CopyButton";
import type { Subscription, Price, PrepayResponse, Merchant } from "@/lib/types";

export default function SubscriptionDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const [sub, setSub] = useState<Subscription | null>(null);
  const [price, setPrice] = useState<Price | null>(null);
  const [merchant, setMerchant] = useState<Merchant | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Action states
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Cancel confirm dialog
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
  const [cancelInput, setCancelInput] = useState("");

  // Phase 8B: Prepay dialog
  const [prepayDialogOpen, setPrepayDialogOpen] = useState(false);
  const [prepayPeriods, setPrepayPeriods] = useState<number>(3);
  const [prepayResult, setPrepayResult] = useState<PrepayResponse | null>(null);

  useEffect(() => {
    fetchSubscription();
    api.get<Price>("/price").then(setPrice).catch(() => {});
    api.get<Merchant>("/merchants/me").then(setMerchant).catch(() => {});
  }, [id]);

  async function fetchSubscription() {
    try {
      const data = await api.get<Subscription>(`/subscriptions/${id}`);
      setSub(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load subscription");
    } finally {
      setLoading(false);
    }
  }

  async function handleAction(action: "pause" | "resume") {
    setActionLoading(action);
    setActionError(null);
    try {
      await api.post(`/subscriptions/${id}/${action}`, {});
      await fetchSubscription();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : `Failed to ${action}`);
    } finally {
      setActionLoading(null);
    }
  }

  async function handleCancel() {
    if (cancelInput !== "CANCEL") return;
    setActionLoading("cancel");
    setActionError(null);
    try {
      await api.post(`/subscriptions/${id}/cancel`, {});
      setCancelDialogOpen(false);
      setCancelInput("");
      await fetchSubscription();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to cancel");
    } finally {
      setActionLoading(null);
    }
  }

  async function handlePrepay() {
    setActionLoading("prepay");
    setActionError(null);
    setPrepayResult(null);
    try {
      const result = await api.post<PrepayResponse>(
        `/subscriptions/${id}/prepay`,
        { periods: prepayPeriods }
      );
      setPrepayResult(result);
      await fetchSubscription();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to create prepay invoice");
    } finally {
      setActionLoading(null);
    }
  }

  function fiatEstimate(amountAtomic: string): string {
    if (!price) return "";
    try {
      const xmr = Number(BigInt(amountAtomic)) / 1e12;
      return `~$${(xmr * price.usd).toFixed(2)}`;
    } catch {
      return "";
    }
  }

  const plans = merchant?.prepay_plans || [];
  const canPrepay = sub?.status === "active" || sub?.status === "past_due";
  const hasPrepayPlans = plans.length > 0;

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-32 bg-gb-card rounded animate-pulse" />
        <div className="gb-card h-64 animate-pulse" />
      </div>
    );
  }

  if (error || !sub) {
    return (
      <div className="space-y-6">
        <Link
          href="/dashboard/subscriptions"
          className="inline-flex items-center gap-2 text-sm text-gb-text-secondary hover:text-gb-accent transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Subscriptions
        </Link>
        <div className="gb-card text-center py-12">
          <XCircle className="w-12 h-12 mx-auto mb-3 text-gb-error opacity-50" />
          <p className="text-gb-error">{error || "Subscription not found"}</p>
        </div>
      </div>
    );
  }

  const isTerminal = sub.status === "cancelled" || sub.status === "expired";
  const isTrialing = sub.status === "trialing";
  const canPause = sub.status === "active";
  const canResume = sub.status === "paused";
  const canCancel = !isTerminal;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            href="/dashboard/subscriptions"
            className="p-2 rounded-gb border border-gb-border text-gb-text-secondary hover:text-gb-text-primary hover:border-gb-accent transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="font-heading text-2xl font-bold text-gb-text-primary">
                Subscription
              </h1>
              <StatusBadge status={sub.status} type="subscription" size="md" />
            </div>
            <p className="text-gb-text-secondary text-xs font-mono mt-1">
              {sub.id}
            </p>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          {canPrepay && hasPrepayPlans && (
            <button
              onClick={() => { setPrepayDialogOpen(true); setPrepayResult(null); }}
              disabled={actionLoading !== null}
              className="gb-btn-secondary flex items-center gap-2 text-gb-accent hover:border-gb-accent disabled:opacity-50"
            >
              <CreditCard className="w-4 h-4" />
              Prepay
            </button>
          )}
          {canPause && (
            <button
              onClick={() => handleAction("pause")}
              disabled={actionLoading !== null}
              className="gb-btn-secondary flex items-center gap-2 text-blue-400 hover:border-blue-400 disabled:opacity-50"
            >
              {actionLoading === "pause" ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Pause className="w-4 h-4" />
              )}
              Pause
            </button>
          )}
          {canResume && (
            <button
              onClick={() => handleAction("resume")}
              disabled={actionLoading !== null}
              className="gb-btn-secondary flex items-center gap-2 text-gb-success hover:border-gb-success disabled:opacity-50"
            >
              {actionLoading === "resume" ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              Resume
            </button>
          )}
          {canCancel && (
            <button
              onClick={() => setCancelDialogOpen(true)}
              disabled={actionLoading !== null}
              className="gb-btn-secondary flex items-center gap-2 text-gb-error hover:border-gb-error disabled:opacity-50"
            >
              <Ban className="w-4 h-4" />
              Cancel
            </button>
          )}
        </div>
      </div>

      {actionError && (
        <div className="p-3 rounded-gb bg-gb-error/10 border border-gb-error/30 text-gb-error text-sm">
          {actionError}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column */}
        <div className="lg:col-span-2 space-y-6">
          {/* Amount & Interval */}
          <div className="gb-card space-y-4">
            <h2 className="font-heading text-lg font-semibold text-gb-text-primary">
              Billing
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <p className="text-xs text-gb-text-secondary uppercase tracking-wider">
                  Amount per Period
                </p>
                <p className="text-xl font-mono font-bold text-gb-text-primary mt-1">
                  {formatXMR(sub.amount_atomic)} XMR
                </p>
                {price && (
                  <p className="text-sm text-gb-text-secondary">
                    {fiatEstimate(sub.amount_atomic)}
                  </p>
                )}
              </div>
              <div>
                <p className="text-xs text-gb-text-secondary uppercase tracking-wider">
                  Interval
                </p>
                <p className="text-xl font-bold text-gb-text-primary mt-1">
                  {sub.interval_days} day{sub.interval_days !== 1 ? "s" : ""}
                </p>
              </div>
              <div>
                <p className="text-xs text-gb-text-secondary uppercase tracking-wider">
                  Next Due
                </p>
                <p className="text-xl font-bold text-gb-text-primary mt-1">
                  {isTerminal || !sub.next_due_at
                    ? "—"
                    : new Date(sub.next_due_at).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                      })}
                </p>
              </div>
            </div>
            {/* Phase 8B: Prepaid until badge */}
            {sub.prepaid_until && (
              <div className="flex items-center gap-2 mt-2 p-3 rounded-gb bg-gb-accent/10 border border-gb-accent/30">
                <CalendarCheck className="w-4 h-4 text-gb-accent shrink-0" />
                <p className="text-sm text-gb-accent">
                  Prepaid until{" "}
                  {new Date(sub.prepaid_until).toLocaleDateString("en-US", {
                    month: "long",
                    day: "numeric",
                    year: "numeric",
                  })}
                </p>
              </div>
            )}
          </div>

          {/* Details */}
          <div className="gb-card space-y-3">
            <h2 className="font-heading text-lg font-semibold text-gb-text-primary">
              Details
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-gb-text-secondary">Customer</p>
                <Link
                  href="/dashboard/customers"
                  className="text-gb-accent hover:underline font-mono"
                >
                  {sub.customer?.external_id ||
                    sub.customer?.email ||
                    sub.customer_id.slice(0, 12) + "..."}
                </Link>
              </div>
              <div>
                <p className="text-gb-text-secondary">Customer Email</p>
                <p className="text-gb-text-primary">
                  {sub.customer?.email || "—"}
                </p>
              </div>
              <div>
                <p className="text-gb-text-secondary">Grace (Soft / Hard)</p>
                <p className="text-gb-text-primary font-mono">
                  {sub.grace_days_soft}d / {sub.grace_days_hard}d
                </p>
              </div>
              {sub.trial_days && (
                <div>
                  <p className="text-gb-text-secondary">Trial Period</p>
                  <p className="text-purple-400 font-mono">
                    {sub.trial_days}d{sub.trial_end_at ? " (ends " + new Date(sub.trial_end_at).toLocaleDateString("en-US", { month: "short", day: "numeric" }) + ")" : ""}
                  </p>
                </div>
              )}
              <div>
                <p className="text-gb-text-secondary">Created</p>
                <p className="text-gb-text-primary">
                  {formatDate(sub.created_at)}
                </p>
              </div>
              {sub.cancelled_at && (
                <div>
                  <p className="text-gb-text-secondary">Cancelled</p>
                  <p className="text-gb-error">
                    {formatDate(sub.cancelled_at)}
                  </p>
                </div>
              )}
            </div>

            {/* Metadata */}
            {sub.metadata && Object.keys(sub.metadata).length > 0 && (
              <div className="pt-2">
                <p className="text-gb-text-secondary text-sm mb-1">Metadata</p>
                <pre className="text-xs font-mono text-gb-text-primary bg-gb-bg p-3 rounded-gb border border-gb-border overflow-x-auto">
                  {JSON.stringify(sub.metadata, null, 2)}
                </pre>
              </div>
            )}
          </div>

          {/* Payment History */}
          <div className="gb-card space-y-3">
            <h2 className="font-heading text-lg font-semibold text-gb-text-primary">
              Payment History ({sub.payments?.length || 0})
            </h2>
            {!sub.payments || sub.payments.length === 0 ? (
              <p className="text-sm text-gb-text-secondary py-4 text-center">
                No payments yet
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gb-border">
                      <th className="text-left text-xs text-gb-text-secondary font-medium pb-2 pr-4">
                        Period
                      </th>
                      <th className="text-left text-xs text-gb-text-secondary font-medium pb-2 pr-4">
                        Invoice
                      </th>
                      <th className="text-left text-xs text-gb-text-secondary font-medium pb-2 pr-4">
                        Status
                      </th>
                      <th className="text-right text-xs text-gb-text-secondary font-medium pb-2">
                        Paid
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sub.payments.map((pmt) => (
                      <tr
                        key={pmt.id}
                        className="border-b border-gb-border/50 last:border-0"
                      >
                        <td className="py-2 pr-4">
                          <span className="text-sm text-gb-text-primary">
                            {new Date(pmt.period_start).toLocaleDateString(
                              "en-US",
                              { month: "short", day: "numeric" }
                            )}{" "}
                            →{" "}
                            {new Date(pmt.period_end).toLocaleDateString(
                              "en-US",
                              { month: "short", day: "numeric" }
                            )}
                          </span>
                        </td>
                        <td className="py-2 pr-4">
                          <Link
                            href={`/dashboard/invoices/${pmt.invoice_id}`}
                            className="font-mono text-xs text-gb-accent hover:underline"
                          >
                            {pmt.invoice_id.slice(0, 8)}...
                          </Link>
                        </td>
                        <td className="py-2 pr-4">
                          <StatusBadge
                            status={pmt.invoice_status}
                            type="invoice"
                          />
                        </td>
                        <td className="py-2 text-right">
                          <span className="text-sm text-gb-text-secondary">
                            {pmt.paid_at ? timeAgo(pmt.paid_at) : "—"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Right column — status info */}
        <div className="space-y-6">
          <div className="gb-card space-y-3">
            <h2 className="font-heading text-sm font-semibold text-gb-text-secondary uppercase tracking-wider">
              Status Info
            </h2>
            {sub.status === "active" && (
              <div className="flex items-start gap-2 text-sm">
                <CheckCircle className="w-4 h-4 text-gb-success mt-0.5 shrink-0" />
                <p className="text-gb-text-secondary">
                  Subscription is active. Next invoice will be generated{" "}
                  {sub.next_due_at ? timeAgo(sub.next_due_at) : "soon"}.
                </p>
              </div>
            )}
            {sub.status === "paused" && (
              <div className="flex items-start gap-2 text-sm">
                <Pause className="w-4 h-4 text-blue-400 mt-0.5 shrink-0" />
                <p className="text-gb-text-secondary">
                  Subscription is paused. No invoices will be generated until
                  resumed.
                </p>
              </div>
            )}
            {sub.status === "past_due" && (
              <div className="flex items-start gap-2 text-sm">
                <AlertTriangle className="w-4 h-4 text-gb-warning mt-0.5 shrink-0" />
                <p className="text-gb-text-secondary">
                  Payment is overdue. The subscription will expire after the
                  hard grace period ({sub.grace_days_hard} days).
                </p>
              </div>
            )}
            {sub.status === "cancelled" && (
              <div className="flex items-start gap-2 text-sm">
                <Ban className="w-4 h-4 text-gb-text-secondary mt-0.5 shrink-0" />
                <p className="text-gb-text-secondary">
                  This subscription was cancelled
                  {sub.cancelled_at ? ` on ${formatDate(sub.cancelled_at)}` : ""}.
                </p>
              </div>
            )}
            {sub.status === "expired" && (
              <div className="flex items-start gap-2 text-sm">
                <XCircle className="w-4 h-4 text-gb-error mt-0.5 shrink-0" />
                <p className="text-gb-text-secondary">
                  This subscription expired due to non-payment after the grace
                  period.
                </p>
              </div>
            )}
            {sub.status === "trialing" && (
              <div className="flex items-start gap-2 text-sm">
                <Clock className="w-4 h-4 text-purple-400 mt-0.5 shrink-0" />
                <p className="text-gb-text-secondary">
                  Trial period active ({sub.trial_days} days). No invoices until trial ends
                  {sub.trial_end_at ? ` on ${formatDate(sub.trial_end_at)}` : ""}.
                </p>
              </div>
            )}
          </div>

          {/* Subscription ID copy */}
          <div className="gb-card space-y-3">
            <h2 className="font-heading text-sm font-semibold text-gb-text-secondary uppercase tracking-wider">
              Subscription ID
            </h2>
            <div className="flex items-center gap-2 bg-gb-bg p-3 rounded-gb border border-gb-border">
              <p className="font-mono text-xs text-gb-text-primary break-all flex-1">
                {sub.id}
              </p>
              <CopyButton text={sub.id} label="" />
            </div>
          </div>
        </div>
      </div>

      {/* Cancel confirmation dialog */}
      {cancelDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => {
              setCancelDialogOpen(false);
              setCancelInput("");
            }}
          />
          <div className="relative bg-gb-sidebar border border-gb-border rounded-gb p-6 w-full max-w-md mx-4 space-y-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-full bg-gb-error/10">
                <Ban className="w-5 h-5 text-gb-error" />
              </div>
              <h2 className="font-heading text-lg font-semibold text-gb-text-primary">
                Cancel Subscription
              </h2>
            </div>
            <p className="text-sm text-gb-text-secondary">
              This action is permanent. The subscription will be cancelled
              immediately and no further invoices will be generated.
            </p>
            <div>
              <label className="block text-sm font-medium text-gb-text-secondary mb-1.5">
                Type <span className="font-mono text-gb-error">CANCEL</span> to
                confirm
              </label>
              <input
                type="text"
                value={cancelInput}
                onChange={(e) => setCancelInput(e.target.value)}
                placeholder="CANCEL"
                className="gb-input w-full font-mono"
                autoFocus
              />
            </div>
            <div className="flex items-center gap-3 pt-1">
              <button
                onClick={handleCancel}
                disabled={cancelInput !== "CANCEL" || actionLoading === "cancel"}
                className="px-4 py-2 rounded-gb text-sm font-medium bg-gb-error text-white hover:bg-gb-error/80 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {actionLoading === "cancel" && (
                  <Loader2 className="w-4 h-4 animate-spin" />
                )}
                Cancel Subscription
              </button>
              <button
                onClick={() => {
                  setCancelDialogOpen(false);
                  setCancelInput("");
                }}
                className="gb-btn-secondary"
              >
                Go Back
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Phase 8B: Prepay dialog */}
      {prepayDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setPrepayDialogOpen(false)}
          />
          <div className="relative bg-gb-sidebar border border-gb-border rounded-gb p-6 w-full max-w-md mx-4 space-y-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-full bg-gb-accent/10">
                <CreditCard className="w-5 h-5 text-gb-accent" />
              </div>
              <h2 className="font-heading text-lg font-semibold text-gb-text-primary">
                Pre-pay Subscription
              </h2>
            </div>

            {prepayResult ? (
              <div className="space-y-3">
                <div className="p-3 rounded-gb bg-gb-success/10 border border-gb-success/30">
                  <p className="text-sm text-gb-success">Prepay invoice created!</p>
                </div>
                <div className="text-sm space-y-1">
                  <p className="text-gb-text-secondary">
                    Invoice: <Link href={`/dashboard/invoices/${prepayResult.invoice_id}`} className="text-gb-accent hover:underline font-mono">{prepayResult.invoice_id.slice(0, 12)}...</Link>
                  </p>
                  <p className="text-gb-text-secondary">
                    Total: <span className="text-gb-text-primary font-mono">{prepayResult.total_xmr} XMR</span>
                    {prepayResult.discount_pct > 0 && <span className="text-gb-success ml-1">(-{prepayResult.discount_pct}%)</span>}
                  </p>
                  <p className="text-gb-text-secondary">
                    Prepaid until: <span className="text-gb-text-primary">{new Date(prepayResult.prepaid_until).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}</span>
                  </p>
                </div>
                <button
                  onClick={() => { setPrepayDialogOpen(false); setPrepayResult(null); }}
                  className="gb-btn-secondary w-full"
                >
                  Close
                </button>
              </div>
            ) : (
              <>
                <p className="text-sm text-gb-text-secondary">
                  Pay multiple periods upfront with a discount.
                </p>

                <div>
                  <label className="block text-sm font-medium text-gb-text-secondary mb-2">Select plan</label>
                  <div className="space-y-2">
                    {plans.map((plan) => {
                      const total = Number(sub.amount_xmr) * plan.periods * (1 - plan.discount_pct / 100);
                      return (
                        <button
                          key={plan.periods}
                          onClick={() => setPrepayPeriods(plan.periods)}
                          className={`w-full text-left p-3 rounded-gb border transition-colors ${
                            prepayPeriods === plan.periods
                              ? "border-gb-accent bg-gb-accent/10"
                              : "border-gb-border hover:border-gb-accent/50"
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-gb-text-primary">
                              {plan.periods} period{plan.periods > 1 ? "s" : ""}
                              {plan.discount_pct > 0 && (
                                <span className="ml-2 text-xs text-gb-success">-{plan.discount_pct}%</span>
                              )}
                            </span>
                            <span className="text-sm font-mono text-gb-text-primary">
                              {total.toFixed(6)} XMR
                            </span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="flex items-center gap-3 pt-1">
                  <button
                    onClick={handlePrepay}
                    disabled={actionLoading === "prepay"}
                    className="px-4 py-2 rounded-gb text-sm font-medium bg-gb-accent text-white hover:bg-gb-accent/80 disabled:opacity-50 flex items-center gap-2"
                  >
                    {actionLoading === "prepay" && <Loader2 className="w-4 h-4 animate-spin" />}
                    Create Prepay Invoice
                  </button>
                  <button
                    onClick={() => setPrepayDialogOpen(false)}
                    className="gb-btn-secondary"
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
