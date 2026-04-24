"use client";
import { useEffect, useState, useCallback } from "react";
import { Plus, FileText } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatXMR, formatFiat, timeAgo } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import Pagination from "@/components/Pagination";
import EmptyState from "@/components/EmptyState";
import type { Invoice, CursorResponse } from "@/lib/types";

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "All Statuses" },
  { value: "pending", label: "Pending" },
  { value: "paid", label: "Paid" },
  { value: "expired", label: "Expired" },
  { value: "partially_paid", label: "Partially Paid" },
  { value: "overpaid", label: "Overpaid" },
  { value: "late_paid", label: "Late Paid" },
  { value: "cancelled", label: "Cancelled" },
];

const LIMIT = 20;

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const [prevCursors, setPrevCursors] = useState<(string | null)[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchInvoices = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set("limit", LIMIT.toString());
      if (cursor) params.set("starting_after", cursor);
      if (statusFilter) params.set("status", statusFilter);

      const data = await api.get<CursorResponse<Invoice>>(`/invoices?${params}`);
      setInvoices(data.data);
      setHasMore(data.has_more);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load invoices");
    } finally {
      setLoading(false);
    }
  }, [cursor, statusFilter]);

  useEffect(() => {
    fetchInvoices();
  }, [fetchInvoices]);

  const handleStatusChange = (value: string) => {
    setStatusFilter(value);
    setCursor(null);
    setPrevCursors([]);
  };

  const handleNext = () => {
    if (invoices.length === 0 || !hasMore) return;
    setPrevCursors([...prevCursors, cursor]);
    setCursor(invoices[invoices.length - 1].id);
  };

  const handlePrev = () => {
    if (prevCursors.length === 0) return;
    const prev = prevCursors[prevCursors.length - 1];
    setPrevCursors(prevCursors.slice(0, -1));
    setCursor(prev);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-2xl font-bold text-gb-text-primary">
            Invoices
          </h1>
        </div>
        <Link
          href="/dashboard/invoices/new"
          className="gb-btn-primary flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          New Invoice
        </Link>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <div className="relative">
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
        ) : invoices.length === 0 ? (
          <EmptyState
            icon={FileText}
            title={statusFilter ? "No invoices match this filter" : "No invoices yet"}
            description={
              statusFilter
                ? "Try changing the status filter"
                : "Create your first invoice to start accepting payments"
            }
            action={
              !statusFilter ? (
                <Link
                  href="/dashboard/invoices/new"
                  className="gb-btn-primary inline-flex items-center gap-2"
                >
                  <Plus className="w-4 h-4" />
                  Create Invoice
                </Link>
              ) : undefined
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
                      Amount
                    </th>
                    <th className="text-left text-xs text-gb-text-secondary font-medium pb-3 pr-4 hidden md:table-cell">
                      Fiat
                    </th>
                    <th className="text-left text-xs text-gb-text-secondary font-medium pb-3 pr-4 hidden lg:table-cell">
                      Description
                    </th>
                    <th className="text-right text-xs text-gb-text-secondary font-medium pb-3">
                      Created
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((inv) => (
                    <tr
                      key={inv.id}
                      className="border-b border-gb-border/50 last:border-0 hover:bg-gb-border/10 transition-colors"
                    >
                      <td className="py-3 pr-4">
                        <StatusBadge status={inv.status} type="invoice" />
                      </td>
                      <td className="py-3 pr-4">
                        <span className="font-mono text-sm text-gb-text-primary">
                          {formatXMR(inv.amount_atomic)} XMR
                        </span>
                      </td>
                      <td className="py-3 pr-4 hidden md:table-cell">
                        <span className="text-sm text-gb-text-secondary">
                          {formatFiat(inv.fiat_amount, inv.fiat_currency)}
                        </span>
                      </td>
                      <td className="py-3 pr-4 hidden lg:table-cell">
                        <span className="text-sm text-gb-text-secondary truncate max-w-[200px] block">
                          {inv.description || "\u2014"}
                        </span>
                      </td>
                      <td className="py-3 text-right">
                        <Link
                          href={`/dashboard/invoices/${inv.id}`}
                          className="text-sm text-gb-accent hover:underline"
                        >
                          {timeAgo(inv.created_at)}
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              hasMore={hasMore}
              hasPrev={prevCursors.length > 0}
              onNext={handleNext}
              onPrev={handlePrev}
              loading={loading}
            />
          </>
        )}
      </div>
    </div>
  );
}
