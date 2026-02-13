"use client";
import { useEffect, useState, useCallback } from "react";
import { Plus, FileText, Search } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatXMR, formatFiat, timeAgo } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import Pagination from "@/components/Pagination";
import EmptyState from "@/components/EmptyState";
import type { Invoice, InvoiceListResponse, InvoiceStatus } from "@/lib/types";

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
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchInvoices = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set("limit", LIMIT.toString());
      params.set("offset", offset.toString());
      if (statusFilter) params.set("status", statusFilter);

      const data = await api.get<InvoiceListResponse>(`/invoices?${params}`);
      setInvoices(data.invoices);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load invoices");
    } finally {
      setLoading(false);
    }
  }, [offset, statusFilter]);

  useEffect(() => {
    fetchInvoices();
  }, [fetchInvoices]);

  const handleStatusChange = (value: string) => {
    setStatusFilter(value);
    setOffset(0);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-2xl font-bold text-gb-text-primary">
            Invoices
          </h1>
          <p className="text-gb-text-secondary text-sm mt-1">
            {total} invoice{total !== 1 ? "s" : ""} total
          </p>
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
                    <th className="text-left text-xs text-gb-text-secondary font-medium pb-3 pr-4 hidden sm:table-cell">
                      External ID
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
                          {inv.description || "—"}
                        </span>
                      </td>
                      <td className="py-3 pr-4 hidden sm:table-cell">
                        <span className="text-sm text-gb-text-secondary font-mono">
                          {inv.external_id || "—"}
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
