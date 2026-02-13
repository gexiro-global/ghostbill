"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Loader2,
  XCircle,
  Clock,
  CheckCircle,
  ExternalLink,
} from "lucide-react";
import { api } from "@/lib/api";
import { formatXMR, formatFiat, formatDate, timeAgo, truncateHash } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import CopyButton from "@/components/CopyButton";
import InvoiceQR from "@/components/InvoiceQR";
import type { Invoice } from "@/lib/types";

export default function InvoiceDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchInvoice() {
      try {
        const data = await api.get<Invoice>(`/invoices/${id}`);
        setInvoice(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load invoice");
      } finally {
        setLoading(false);
      }
    }
    fetchInvoice();
  }, [id]);

  async function handleCancel() {
    if (!confirm("Are you sure you want to cancel this invoice?")) return;
    setCancelling(true);
    setCancelError(null);
    try {
      const updated = await api.post<Invoice>(`/invoices/${id}/cancel`, {});
      setInvoice(updated);
    } catch (err) {
      setCancelError(err instanceof Error ? err.message : "Failed to cancel");
    } finally {
      setCancelling(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-32 bg-gb-card rounded animate-pulse" />
        <div className="gb-card h-64 animate-pulse" />
      </div>
    );
  }

  if (error || !invoice) {
    return (
      <div className="space-y-6">
        <Link
          href="/dashboard/invoices"
          className="inline-flex items-center gap-2 text-sm text-gb-text-secondary hover:text-gb-accent transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Invoices
        </Link>
        <div className="gb-card text-center py-12">
          <XCircle className="w-12 h-12 mx-auto mb-3 text-gb-error opacity-50" />
          <p className="text-gb-error">{error || "Invoice not found"}</p>
        </div>
      </div>
    );
  }

  const isPending = invoice.status === "pending";
  const paidAtomic = BigInt(invoice.paid_atomic || "0");
  const amountAtomic = BigInt(invoice.amount_atomic);
  const progressPercent =
    amountAtomic > BigInt(0)
      ? Math.min(Number((paidAtomic * BigInt(100)) / amountAtomic), 100)
      : 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            href="/dashboard/invoices"
            className="p-2 rounded-gb border border-gb-border text-gb-text-secondary hover:text-gb-text-primary hover:border-gb-accent transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="font-heading text-2xl font-bold text-gb-text-primary">
                Invoice
              </h1>
              <StatusBadge status={invoice.status} type="invoice" />
            </div>
            <p className="text-gb-text-secondary text-xs font-mono mt-1">
              {invoice.id}
            </p>
          </div>
        </div>
        {isPending && (
          <button
            onClick={handleCancel}
            disabled={cancelling}
            className="gb-btn-secondary flex items-center gap-2 text-gb-error hover:border-gb-error disabled:opacity-50"
          >
            {cancelling ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <XCircle className="w-4 h-4" />
            )}
            Cancel Invoice
          </button>
        )}
      </div>

      {cancelError && (
        <div className="p-3 rounded-gb bg-gb-error/10 border border-gb-error/30 text-gb-error text-sm">
          {cancelError}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column — details */}
        <div className="lg:col-span-2 space-y-6">
          {/* Amounts */}
          <div className="gb-card space-y-4">
            <h2 className="font-heading text-lg font-semibold text-gb-text-primary">
              Amount
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-gb-text-secondary uppercase tracking-wider">
                  Requested
                </p>
                <p className="text-xl font-mono font-bold text-gb-text-primary mt-1">
                  {formatXMR(invoice.amount_atomic)} XMR
                </p>
                {invoice.fiat_amount && (
                  <p className="text-sm text-gb-text-secondary">
                    {formatFiat(invoice.fiat_amount, invoice.fiat_currency)}
                  </p>
                )}
              </div>
              <div>
                <p className="text-xs text-gb-text-secondary uppercase tracking-wider">
                  Received
                </p>
                <p className="text-xl font-mono font-bold text-gb-text-primary mt-1">
                  {formatXMR(invoice.paid_atomic)} XMR
                </p>
                {/* Progress bar */}
                <div className="mt-2 h-1.5 bg-gb-border/30 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      progressPercent >= 100 ? "bg-gb-success" : "bg-gb-accent"
                    }`}
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Details */}
          <div className="gb-card space-y-3">
            <h2 className="font-heading text-lg font-semibold text-gb-text-primary">
              Details
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-gb-text-secondary">Description</p>
                <p className="text-gb-text-primary">{invoice.description || "—"}</p>
              </div>
              <div>
                <p className="text-gb-text-secondary">External ID</p>
                <p className="text-gb-text-primary font-mono">
                  {invoice.external_id || "—"}
                </p>
              </div>
              <div>
                <p className="text-gb-text-secondary">Created</p>
                <p className="text-gb-text-primary">{formatDate(invoice.created_at)}</p>
              </div>
              <div>
                <p className="text-gb-text-secondary">Expires</p>
                <p className={`${isPending ? "text-gb-warning" : "text-gb-text-primary"}`}>
                  {isPending && <Clock className="w-3 h-3 inline mr-1" />}
                  {formatDate(invoice.expires_at)}
                </p>
              </div>
              <div>
                <p className="text-gb-text-secondary">Confirmations Required</p>
                <p className="text-gb-text-primary">{invoice.confirmations_required}</p>
              </div>
              <div>
                <p className="text-gb-text-secondary">Subaddress Index</p>
                <p className="text-gb-text-primary font-mono">{invoice.subaddress_index}</p>
              </div>
            </div>
          </div>

          {/* Subaddress */}
          <div className="gb-card space-y-3">
            <h2 className="font-heading text-lg font-semibold text-gb-text-primary">
              Payment Address
            </h2>
            <div className="flex items-center gap-2 bg-gb-bg p-3 rounded-gb border border-gb-border">
              <p className="font-mono text-xs text-gb-text-primary break-all flex-1">
                {invoice.subaddress}
              </p>
              <CopyButton text={invoice.subaddress} label="" />
            </div>
          </div>

          {/* Payments */}
          <div className="gb-card space-y-3">
            <h2 className="font-heading text-lg font-semibold text-gb-text-primary">
              Payments ({invoice.payments?.length || 0})
            </h2>
            {!invoice.payments || invoice.payments.length === 0 ? (
              <p className="text-sm text-gb-text-secondary py-4 text-center">
                No payments received yet
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gb-border">
                      <th className="text-left text-xs text-gb-text-secondary font-medium pb-2 pr-4">
                        Status
                      </th>
                      <th className="text-left text-xs text-gb-text-secondary font-medium pb-2 pr-4">
                        TX Hash
                      </th>
                      <th className="text-left text-xs text-gb-text-secondary font-medium pb-2 pr-4">
                        Amount
                      </th>
                      <th className="text-left text-xs text-gb-text-secondary font-medium pb-2 pr-4">
                        Confirmations
                      </th>
                      <th className="text-right text-xs text-gb-text-secondary font-medium pb-2">
                        Detected
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {invoice.payments.map((pmt) => (
                      <tr
                        key={pmt.id}
                        className="border-b border-gb-border/50 last:border-0"
                      >
                        <td className="py-2 pr-4">
                          <StatusBadge status={pmt.status} type="payment" />
                        </td>
                        <td className="py-2 pr-4">
                          <div className="flex items-center gap-1">
                            <Link
                              href={`/dashboard/payments/${pmt.id}`}
                              className="font-mono text-xs text-gb-accent hover:underline"
                            >
                              {truncateHash(pmt.tx_hash)}
                            </Link>
                            <CopyButton text={pmt.tx_hash} />
                          </div>
                        </td>
                        <td className="py-2 pr-4">
                          <span className="font-mono text-sm text-gb-text-primary">
                            {formatXMR(pmt.amount_atomic)} XMR
                          </span>
                        </td>
                        <td className="py-2 pr-4">
                          <span className="text-sm text-gb-text-primary">
                            {pmt.confirmations}
                          </span>
                        </td>
                        <td className="py-2 text-right">
                          <span className="text-xs text-gb-text-secondary">
                            {timeAgo(pmt.detected_at)}
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

        {/* Right column — QR code (only for pending) */}
        <div className="space-y-6">
          {isPending && (
            <div className="gb-card flex flex-col items-center space-y-4">
              <h2 className="font-heading text-lg font-semibold text-gb-text-primary">
                Scan to Pay
              </h2>
              <InvoiceQR
                address={invoice.subaddress}
                amountXmr={invoice.amount_xmr}
              />
              <p className="text-xs text-gb-text-secondary text-center">
                Send exactly{" "}
                <span className="font-mono text-gb-text-primary">
                  {formatXMR(invoice.amount_atomic)} XMR
                </span>{" "}
                to the address above
              </p>
            </div>
          )}

          {/* Status info card */}
          <div className="gb-card space-y-3">
            <h2 className="font-heading text-sm font-semibold text-gb-text-secondary uppercase tracking-wider">
              Status Info
            </h2>
            {invoice.status === "pending" && (
              <div className="flex items-start gap-2 text-sm">
                <Clock className="w-4 h-4 text-gb-warning mt-0.5 shrink-0" />
                <p className="text-gb-text-secondary">
                  Waiting for payment. Invoice expires{" "}
                  <span className="text-gb-warning">{timeAgo(invoice.expires_at)}</span>.
                </p>
              </div>
            )}
            {invoice.status === "paid" && (
              <div className="flex items-start gap-2 text-sm">
                <CheckCircle className="w-4 h-4 text-gb-success mt-0.5 shrink-0" />
                <p className="text-gb-text-secondary">
                  Payment confirmed. The full amount has been received.
                </p>
              </div>
            )}
            {invoice.status === "expired" && (
              <div className="flex items-start gap-2 text-sm">
                <XCircle className="w-4 h-4 text-gb-error mt-0.5 shrink-0" />
                <p className="text-gb-text-secondary">
                  Invoice expired before payment was received.
                </p>
              </div>
            )}
            {invoice.status === "partially_paid" && (
              <div className="flex items-start gap-2 text-sm">
                <Clock className="w-4 h-4 text-gb-warning mt-0.5 shrink-0" />
                <p className="text-gb-text-secondary">
                  Only a partial payment was received before expiry.
                </p>
              </div>
            )}
            {invoice.status === "overpaid" && (
              <div className="flex items-start gap-2 text-sm">
                <CheckCircle className="w-4 h-4 text-gb-success mt-0.5 shrink-0" />
                <p className="text-gb-text-secondary">
                  More than the requested amount was received.
                </p>
              </div>
            )}
            {invoice.status === "late_paid" && (
              <div className="flex items-start gap-2 text-sm">
                <CheckCircle className="w-4 h-4 text-gb-warning mt-0.5 shrink-0" />
                <p className="text-gb-text-secondary">
                  Payment was received after the invoice expired.
                </p>
              </div>
            )}
            {invoice.status === "cancelled" && (
              <div className="flex items-start gap-2 text-sm">
                <XCircle className="w-4 h-4 text-gb-text-secondary mt-0.5 shrink-0" />
                <p className="text-gb-text-secondary">
                  This invoice was manually cancelled.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
