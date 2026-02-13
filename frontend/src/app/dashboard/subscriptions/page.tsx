"use client";
import { useEffect, useState, useCallback } from "react";
import { Plus, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { formatXMR, timeAgo } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import Pagination from "@/components/Pagination";
import EmptyState from "@/components/EmptyState";
import type {
  Subscription,
  SubscriptionListResponse,
  Customer,
  CustomerListResponse,
  Price,
} from "@/lib/types";

const STATUS_OPTIONS = [
  { value: "", label: "All Statuses" },
  { value: "active", label: "Active" },
  { value: "paused", label: "Paused" },
  { value: "past_due", label: "Past Due" },
  { value: "cancelled", label: "Cancelled" },
  { value: "expired", label: "Expired" },
];

const LIMIT = 20;

export default function SubscriptionsPage() {
  const router = useRouter();
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [customerFilter, setCustomerFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // For customer filter dropdown + fiat preview
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [price, setPrice] = useState<Price | null>(null);

  // Fetch customers for filter dropdown + price for fiat preview
  useEffect(() => {
    api
      .get<CustomerListResponse>("/customers?limit=100&offset=0")
      .then((d) => setCustomers(d.customers))
      .catch(() => {});
    api
      .get<Price>("/price")
      .then(setPrice)
      .catch(() => {});
  }, []);

  const fetchSubscriptions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set("limit", LIMIT.toString());
      params.set("offset", offset.toString());
      if (statusFilter) params.set("status", statusFilter);
      if (customerFilter) params.set("customer_id", customerFilter);

      const data = await api.get<SubscriptionListResponse>(
        `/subscriptions?${params}`
      );
      setSubscriptions(data.subscriptions);
      setTotal(data.total);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load subscriptions"
      );
    } finally {
      setLoading(false);
    }
  }, [offset, statusFilter, customerFilter]);

  useEffect(() => {
    fetchSubscriptions();
  }, [fetchSubscriptions]);

  const handleStatusChange = (value: string) => {
    setStatusFilter(value);
    setOffset(0);
  };

  const handleCustomerChange = (value: string) => {
    setCustomerFilter(value);
    setOffset(0);
  };

  function fiatEstimate(amountAtomic: string): string {
    if (!price) return "";
    try {
      const xmr = Number(BigInt(amountAtomic)) / 1e12;
      const usd = xmr * price.usd;
      return `~$${usd.toFixed(2)}`;
    } catch {
      return "";
    }
  }

  function formatNextDue(sub: Subscription): string {
    if (sub.status === "cancelled" || sub.status === "expired") return "—";
    if (!sub.next_due_at) return "—";
    const due = new Date(sub.next_due_at);
    const now = new Date();
    const diffMs = due.getTime() - now.getTime();
    const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
    if (diffDays < 0) return `${Math.abs(diffDays)}d overdue`;
    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Tomorrow";
    return due.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }

  function isOverdue(sub: Subscription): boolean {
    if (!sub.next_due_at) return false;
    return new Date(sub.next_due_at).getTime() < Date.now();
  }

  function customerLabel(customerId: string): string {
    const c = customers.find((c) => c.id === customerId);
    return c?.external_id || c?.email || customerId.slice(0, 8) + "...";
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-2xl font-bold text-gb-text-primary">
            Subscriptions
          </h1>
          <p className="text-gb-text-secondary text-sm mt-1">
            {total} subscription{total !== 1 ? "s" : ""} total
          </p>
        </div>
        <Link
          href="/dashboard/subscriptions/new"
          className="gb-btn-primary flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          New Subscription
        </Link>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4 flex-wrap">
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
        <select
          value={customerFilter}
          onChange={(e) => handleCustomerChange(e.target.value)}
          className="gb-input pr-8 appearance-none cursor-pointer text-sm min-w-[180px]"
        >
          <option value="">All Customers</option>
          {customers.map((c) => (
            <option key={c.id} value={c.id}>
              {c.external_id || c.email || c.id.slice(0, 8) + "..."}
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
              <div
                key={i}
                className="h-12 bg-gb-border/20 rounded animate-pulse"
              />
            ))}
          </div>
        ) : subscriptions.length === 0 ? (
          <EmptyState
            icon={RefreshCw}
            title={
              statusFilter || customerFilter
                ? "No subscriptions match these filters"
                : "No subscriptions yet"
            }
            description={
              statusFilter || customerFilter
                ? "Try changing the filters"
                : "Create a subscription to start recurring billing."
            }
            action={
              !statusFilter && !customerFilter ? (
                <Link
                  href="/dashboard/subscriptions/new"
                  className="gb-btn-primary inline-flex items-center gap-2"
                >
                  <Plus className="w-4 h-4" />
                  Create Subscription
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
                      Customer
                    </th>
                    <th className="text-left text-xs text-gb-text-secondary font-medium pb-3 pr-4">
                      Amount
                    </th>
                    <th className="text-left text-xs text-gb-text-secondary font-medium pb-3 pr-4 hidden sm:table-cell">
                      Interval
                    </th>
                    <th className="text-right text-xs text-gb-text-secondary font-medium pb-3">
                      Next Due
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {subscriptions.map((sub) => (
                    <tr
                      key={sub.id}
                      onClick={() =>
                        router.push(`/dashboard/subscriptions/${sub.id}`)
                      }
                      className="border-b border-gb-border/50 last:border-0 hover:bg-gb-border/10 transition-colors cursor-pointer"
                    >
                      <td className="py-3 pr-4">
                        <StatusBadge
                          status={sub.status}
                          type="subscription"
                        />
                      </td>
                      <td className="py-3 pr-4">
                        <span className="text-sm text-gb-text-primary font-mono">
                          {customerLabel(sub.customer_id)}
                        </span>
                      </td>
                      <td className="py-3 pr-4">
                        <div>
                          <span className="font-mono text-sm text-gb-text-primary font-medium">
                            {formatXMR(sub.amount_atomic)} XMR
                          </span>
                          {price && (
                            <span className="block text-xs text-gb-text-secondary">
                              {fiatEstimate(sub.amount_atomic)}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3 pr-4 hidden sm:table-cell">
                        <span className="text-sm text-gb-text-primary">
                          {sub.interval_days} day{sub.interval_days !== 1 ? "s" : ""}
                        </span>
                      </td>
                      <td className="py-3 text-right">
                        <span
                          className={`text-sm ${
                            isOverdue(sub)
                              ? "text-gb-error font-medium"
                              : "text-gb-text-secondary"
                          }`}
                        >
                          {formatNextDue(sub)}
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
