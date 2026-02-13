"use client";
import { useEffect, useState, useCallback } from "react";
import { Coins } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatXMR, timeAgo, truncateHash } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import Pagination from "@/components/Pagination";
import EmptyState from "@/components/EmptyState";
import CopyButton from "@/components/CopyButton";
import type { Payment, PaymentListResponse } from "@/lib/types";

const STATUS_OPTIONS = [
  { value: "", label: "All Statuses" },
  { value: "detected", label: "Detected" },
  { value: "confirmed", label: "Confirmed" },
  { value: "orphaned", label: "Orphaned" },
];

const LIMIT = 20;

export default function PaymentsPage() {
  const [payments, setPayments] = useState<Payment[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPayments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set("limit", LIMIT.toString());
      params.set("offset", offset.toString());
      if (statusFilter) params.set("status", statusFilter);

      const data = await api.get<PaymentListResponse>(`/payments?${params}`);
      setPayments(data.payments);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load payments");
    } finally {
      setLoading(false);
    }
  }, [offset, statusFilter]);

  useEffect(() => {
    fetchPayments();
  }, [fetchPayments]);

  const handleStatusChange = (value: string) => {
    setStatusFilter(value);
    setOffset(0);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-heading text-2xl font-bold text-gb-text-primary">
          Payments
        </h1>
        <p className="text-gb-text-secondary text-sm mt-1">
          {total} payment{total !== 1 ? "s" : ""} total
        </p>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <select
          value={statusFilter}
          onChange={(e) => handleStatusChange(e.target.value)}
          className="gb-input pr-8 appearance-none cursor-pointer text-sm min-w-[160px]"
        >
          {STATUS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Error */}
      {error && (
        <div className="gb-card border-gb-error/50 text-gb-error text-sm">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="gb-card">
        {loading ? (
          <div className="space-y-4">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-12 bg-gb-border/20 rounded animate-pulse" />
            ))}
          </div>
        ) : payments.length === 0 ? (
          <EmptyState
            icon={Coins}
            title={statusFilter ? "No payments match this filter" : "No payments yet"}
            description={
              statusFilter
                ? "Try changing the status filter"
                : "Payments will appear here when transactions are detected"
            }
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gb-border">
                    <th className="text-left text-xs text-gb-text-secondary font-medium pb-3 pr-4">
                      Status
                    </th>
                    <th className="text-left text-xs text-gb-text-secondary font-medium pb-3 pr-4">
                      TX Hash
                    </th>
                    <th className="text-left text-xs text-gb-text-secondary font-medium pb-3 pr-4">
                      Amount
                    </th>
                    <th className="text-left text-xs text-gb-text-secondary font-medium pb-3 pr-4 hidden sm:table-cell">
                      Confirmations
                    </th>
                    <th className="text-left text-xs text-gb-text-secondary font-medium pb-3 pr-4 hidden md:table-cell">
                      Invoice
                    </th>
                    <th className="text-right text-xs text-gb-text-secondary font-medium pb-3">
                      Detected
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {payments.map((pmt) => (
                    <tr
                      key={pmt.id}
                      className="border-b border-gb-border/50 last:border-0 hover:bg-gb-border/10 transition-colors"
                    >
                      <td className="py-3 pr-4">
                        <StatusBadge status={pmt.status} type="payment" />
                      </td>
                      <td className="py-3 pr-4">
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
                      <td className="py-3 pr-4">
                        <span className="font-mono text-sm text-gb-text-primary">
                          {formatXMR(pmt.amount_atomic)} XMR
                        </span>
                      </td>
                      <td className="py-3 pr-4 hidden sm:table-cell">
                        <span className="text-sm text-gb-text-primary">
                          {pmt.confirmations}
                        </span>
                      </td>
                      <td className="py-3 pr-4 hidden md:table-cell">
                        <Link
                          href={`/dashboard/invoices/${pmt.invoice_id}`}
                          className="text-xs text-gb-accent hover:underline font-mono"
                        >
                          {truncateHash(pmt.invoice_id, 4, 4)}
                        </Link>
                      </td>
                      <td className="py-3 text-right">
                        <span className="text-sm text-gb-text-secondary">
                          {timeAgo(pmt.detected_at)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              total={total}
              limit={LIMIT}
              offset={offset}
              onPageChange={setOffset}
            />
          </>
        )}
      </div>
    </div>
  );
}
