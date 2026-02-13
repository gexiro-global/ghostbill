"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, XCircle, CheckCircle, Clock, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import { formatXMR, formatDate, timeAgo } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import CopyButton from "@/components/CopyButton";
import type { Payment } from "@/lib/types";

export default function PaymentDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const [payment, setPayment] = useState<Payment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchPayment() {
      try {
        const data = await api.get<Payment>(`/payments/${id}`);
        setPayment(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load payment");
      } finally {
        setLoading(false);
      }
    }
    fetchPayment();
  }, [id]);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-32 bg-gb-card rounded animate-pulse" />
        <div className="gb-card h-64 animate-pulse" />
      </div>
    );
  }

  if (error || !payment) {
    return (
      <div className="space-y-6">
        <Link
          href="/dashboard/payments"
          className="inline-flex items-center gap-2 text-sm text-gb-text-secondary hover:text-gb-accent transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Payments
        </Link>
        <div className="gb-card text-center py-12">
          <XCircle className="w-12 h-12 mx-auto mb-3 text-gb-error opacity-50" />
          <p className="text-gb-error">{error || "Payment not found"}</p>
        </div>
      </div>
    );
  }

  // Confirmation progress (10 = fully confirmed typical)
  const confirmTarget = 10;
  const confirmPercent = Math.min((payment.confirmations / confirmTarget) * 100, 100);

  return (
    <div className="max-w-3xl space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link
          href="/dashboard/payments"
          className="p-2 rounded-gb border border-gb-border text-gb-text-secondary hover:text-gb-text-primary hover:border-gb-accent transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-heading text-2xl font-bold text-gb-text-primary">
              Payment
            </h1>
            <StatusBadge status={payment.status} type="payment" />
          </div>
          <p className="text-gb-text-secondary text-xs font-mono mt-1">
            {payment.id}
          </p>
        </div>
      </div>

      {/* Status card */}
      <div className="gb-card space-y-4">
        {payment.status === "detected" && (
          <div className="flex items-start gap-3 p-3 rounded-gb bg-gb-warning/10 border border-gb-warning/20">
            <Clock className="w-5 h-5 text-gb-warning mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-medium text-gb-warning">Awaiting Confirmations</p>
              <p className="text-xs text-gb-text-secondary mt-0.5">
                Transaction detected in mempool. Waiting for blockchain confirmations.
              </p>
            </div>
          </div>
        )}
        {payment.status === "confirmed" && (
          <div className="flex items-start gap-3 p-3 rounded-gb bg-gb-success/10 border border-gb-success/20">
            <CheckCircle className="w-5 h-5 text-gb-success mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-medium text-gb-success">Confirmed</p>
              <p className="text-xs text-gb-text-secondary mt-0.5">
                Payment has been confirmed on the blockchain.
              </p>
            </div>
          </div>
        )}
        {payment.status === "orphaned" && (
          <div className="flex items-start gap-3 p-3 rounded-gb bg-gb-error/10 border border-gb-error/20">
            <AlertTriangle className="w-5 h-5 text-gb-error mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-medium text-gb-error">Orphaned</p>
              <p className="text-xs text-gb-text-secondary mt-0.5">
                This transaction was orphaned and is no longer valid.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Details */}
      <div className="gb-card space-y-4">
        <h2 className="font-heading text-lg font-semibold text-gb-text-primary">
          Transaction Details
        </h2>

        <div className="space-y-4">
          {/* TX Hash */}
          <div>
            <p className="text-xs text-gb-text-secondary uppercase tracking-wider mb-1">
              Transaction Hash
            </p>
            <div className="flex items-center gap-2 bg-gb-bg p-3 rounded-gb border border-gb-border">
              <p className="font-mono text-xs text-gb-text-primary break-all flex-1">
                {payment.tx_hash}
              </p>
              <CopyButton text={payment.tx_hash} />
            </div>
          </div>

          {/* Amount */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-gb-text-secondary uppercase tracking-wider mb-1">
                Amount
              </p>
              <p className="text-xl font-mono font-bold text-gb-text-primary">
                {formatXMR(payment.amount_atomic)} XMR
              </p>
            </div>
            <div>
              <p className="text-xs text-gb-text-secondary uppercase tracking-wider mb-1">
                Confirmations
              </p>
              <p className="text-xl font-mono font-bold text-gb-text-primary">
                {payment.confirmations}
              </p>
              <div className="mt-2 h-1.5 bg-gb-border/30 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    payment.status === "confirmed" ? "bg-gb-success" : "bg-gb-accent"
                  }`}
                  style={{ width: `${confirmPercent}%` }}
                />
              </div>
            </div>
          </div>

          {/* Timestamps & metadata */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-gb-border">
            <div>
              <p className="text-xs text-gb-text-secondary uppercase tracking-wider mb-1">
                Detected At
              </p>
              <p className="text-sm text-gb-text-primary">
                {formatDate(payment.detected_at)}
              </p>
            </div>
            <div>
              <p className="text-xs text-gb-text-secondary uppercase tracking-wider mb-1">
                Confirmed At
              </p>
              <p className="text-sm text-gb-text-primary">
                {payment.confirmed_at ? formatDate(payment.confirmed_at) : "—"}
              </p>
            </div>
            <div>
              <p className="text-xs text-gb-text-secondary uppercase tracking-wider mb-1">
                Block Height
              </p>
              <p className="text-sm text-gb-text-primary font-mono">
                {payment.block_height ?? "Pending"}
              </p>
            </div>
            <div>
              <p className="text-xs text-gb-text-secondary uppercase tracking-wider mb-1">
                Linked Invoice
              </p>
              <Link
                href={`/dashboard/invoices/${payment.invoice_id}`}
                className="text-sm text-gb-accent hover:underline font-mono"
              >
                {payment.invoice_id}
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
