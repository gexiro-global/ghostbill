"use client";
import { useEffect, useState } from "react";
import { FileText, Wallet, TrendingUp, Clock, Plus, AlertTriangle } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatXMR, formatDate, timeAgo } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import type { Merchant, Invoice, Payment, Price, InvoiceListResponse, PaymentListResponse } from "@/lib/types";

interface MetricCardProps {
  title: string;
  value: string;
  subtitle?: string;
  icon: React.ReactNode;
  loading?: boolean;
  warning?: boolean;
}

function MetricCard({ title, value, subtitle, icon, loading, warning }: MetricCardProps) {
  return (
    <div className="gb-card flex items-start justify-between">
      <div>
        <p className="text-sm text-gb-text-secondary font-medium">{title}</p>
        {loading ? (
          <div className="h-8 w-24 bg-gb-border/30 rounded animate-pulse mt-1" />
        ) : (
          <p className="text-2xl font-heading font-bold text-gb-text-primary mt-1">
            {value}
          </p>
        )}
        {subtitle && (
          <p className={`text-xs mt-1 flex items-center gap-1 ${warning ? "text-gb-warning" : "text-gb-text-secondary"}`}>
            {warning && <AlertTriangle className="w-3 h-3" />}
            {subtitle}
          </p>
        )}
      </div>
      <div className="p-3 bg-gb-accent/10 rounded-gb text-gb-accent">
        {icon}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [merchant, setMerchant] = useState<Merchant | null>(null);
  const [totalInvoices, setTotalInvoices] = useState<number>(0);
  const [pendingCount, setPendingCount] = useState<number>(0);
  const [price, setPrice] = useState<Price | null>(null);
  const [recentInvoices, setRecentInvoices] = useState<Invoice[]>([]);
  const [confirmedPayments, setConfirmedPayments] = useState<Payment[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchDashboard() {
      try {
        const [merchantData, allInvoices, pendingInvoices, priceData, payments] =
          await Promise.allSettled([
            api.get<Merchant>("/merchants/me"),
            api.get<InvoiceListResponse>("/invoices?limit=5"),
            api.get<InvoiceListResponse>("/invoices?status=pending&limit=1"),
            api.get<Price>("/price"),
            api.get<PaymentListResponse>("/payments?status=confirmed&limit=50"),
          ]);

        if (merchantData.status === "fulfilled") setMerchant(merchantData.value);
        if (allInvoices.status === "fulfilled") {
          setTotalInvoices(allInvoices.value.total);
          setRecentInvoices(allInvoices.value.invoices);
        }
        if (pendingInvoices.status === "fulfilled") setPendingCount(pendingInvoices.value.total);
        if (priceData.status === "fulfilled") setPrice(priceData.value);
        if (payments.status === "fulfilled") setConfirmedPayments(payments.value.payments);
      } catch {
        // Individual errors handled by allSettled
      } finally {
        setLoading(false);
      }
    }

    fetchDashboard();
  }, []);

  // Calculate total received XMR from confirmed payments
  const totalReceivedAtomic = confirmedPayments.reduce((sum, p) => {
    try {
      return sum + BigInt(p.amount_atomic);
    } catch {
      return sum;
    }
  }, BigInt(0));

  const totalReceivedXmr = formatXMR(totalReceivedAtomic.toString(), 4);

  // Format price display
  const priceDisplay = price ? `$${price.usd.toFixed(2)}` : "—";
  const priceSubtitle = price
    ? price.stale
      ? "Price data may be outdated"
      : `€${price.eur.toFixed(2)} · ${price.source}`
    : "Loading...";

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-2xl font-bold text-gb-text-primary">
            Dashboard
          </h1>
          {merchant && (
            <p className="text-gb-text-secondary mt-1">
              Welcome back, {merchant.name}
            </p>
          )}
        </div>
        <Link
          href="/dashboard/invoices/new"
          className="gb-btn-primary flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          New Invoice
        </Link>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard
          title="Total Invoices"
          value={totalInvoices.toString()}
          subtitle="All time"
          icon={<FileText className="w-5 h-5" />}
          loading={loading}
        />
        <MetricCard
          title="Total Received"
          value={`${totalReceivedXmr} XMR`}
          subtitle={price ? `~$${(parseFloat(totalReceivedXmr) * price.usd).toFixed(2)}` : "Confirmed payments"}
          icon={<Wallet className="w-5 h-5" />}
          loading={loading}
        />
        <MetricCard
          title="XMR Price"
          value={priceDisplay}
          subtitle={priceSubtitle}
          icon={<TrendingUp className="w-5 h-5" />}
          loading={loading}
          warning={price?.stale}
        />
        <MetricCard
          title="Pending"
          value={pendingCount.toString()}
          subtitle="Awaiting payment"
          icon={<Clock className="w-5 h-5" />}
          loading={loading}
        />
      </div>

      {/* Recent invoices */}
      <div className="gb-card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-heading text-lg font-semibold text-gb-text-primary">
            Recent Invoices
          </h2>
          {totalInvoices > 0 && (
            <Link
              href="/dashboard/invoices"
              className="text-sm text-gb-accent hover:underline"
            >
              View all →
            </Link>
          )}
        </div>

        {recentInvoices.length === 0 ? (
          <div className="text-center py-12 text-gb-text-secondary">
            <Wallet className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p>No invoices yet</p>
            <p className="text-sm mt-1">
              Create your first invoice to start accepting Monero payments
            </p>
            <Link
              href="/dashboard/invoices/new"
              className="gb-btn-primary inline-flex items-center gap-2 mt-4"
            >
              <Plus className="w-4 h-4" />
              Create Invoice
            </Link>
          </div>
        ) : (
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
                  <th className="text-left text-xs text-gb-text-secondary font-medium pb-3 pr-4 hidden sm:table-cell">
                    Description
                  </th>
                  <th className="text-right text-xs text-gb-text-secondary font-medium pb-3">
                    Created
                  </th>
                </tr>
              </thead>
              <tbody>
                {recentInvoices.map((inv) => (
                  <tr
                    key={inv.id}
                    className="border-b border-gb-border/50 last:border-0"
                  >
                    <td className="py-3 pr-4">
                      <StatusBadge status={inv.status} type="invoice" />
                    </td>
                    <td className="py-3 pr-4">
                      <span className="font-mono text-sm text-gb-text-primary">
                        {formatXMR(inv.amount_atomic)} XMR
                      </span>
                    </td>
                    <td className="py-3 pr-4 hidden sm:table-cell">
                      <span className="text-sm text-gb-text-secondary truncate max-w-[200px] block">
                        {inv.description || "—"}
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
        )}
      </div>
    </div>
  );
}
