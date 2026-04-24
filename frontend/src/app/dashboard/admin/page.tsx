"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Shield,
  Users,
  FileText,
  Wallet,
  RefreshCw,
  Heart,
  Database,
  Radio,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Loader2,
} from "lucide-react";
import { api } from "@/lib/api";

interface AdminStats {
  merchants_total: number;
  merchants_active: number;
  invoices_total: number;
  invoices_paid: number;
  invoices_pending: number;
  invoices_expired: number;
  payments_total: number;
  payments_confirmed: number;
  total_revenue_atomic: number;
  total_revenue_xmr: string;
  subscriptions_total: number;
  subscriptions_active: number;
  subscriptions_trialing: number;
  webhook_deliveries_pending: number;
  webhook_dlq_unresolved: number;
}

interface AdminHealth {
  status: string;
  app: string;
  version: string;
  detection: Record<string, unknown>;
  database: Record<string, unknown>;
  redis: Record<string, unknown>;
  wallet_rpc: Record<string, unknown>;
  background_tasks: Record<string, unknown>;
}

interface AdminMerchant {
  id: string;
  name: string;
  email: string | null;
  is_active: boolean;
  invoice_count: number;
  subscription_count: number;
  created_at: string;
}

function StatusDot({ ok }: { ok: boolean }) {
  return ok ? (
    <CheckCircle className="w-4 h-4 text-gb-success" />
  ) : (
    <XCircle className="w-4 h-4 text-gb-error" />
  );
}

export default function AdminPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [authorized, setAuthorized] = useState(false);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [health, setHealth] = useState<AdminHealth | null>(null);
  const [merchants, setMerchants] = useState<AdminMerchant[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    checkAccess();
  }, []);

  async function checkAccess() {
    try {
      const me = await api.get<{ is_admin: boolean }>("/admin/me");
      if (!me.is_admin) {
        router.push("/dashboard");
        return;
      }
      setAuthorized(true);
      await Promise.all([fetchStats(), fetchHealth(), fetchMerchants()]);
    } catch {
      router.push("/dashboard");
    } finally {
      setLoading(false);
    }
  }

  async function fetchStats() {
    try {
      const data = await api.get<AdminStats>("/admin/stats");
      setStats(data);
    } catch (err) {
      setError("Failed to load stats");
    }
  }

  async function fetchHealth() {
    try {
      const data = await api.get<AdminHealth>("/admin/health");
      setHealth(data);
    } catch (err) {
      setError("Failed to load health");
    }
  }

  async function fetchMerchants() {
    try {
      const data = await api.get<{ merchants: AdminMerchant[]; total: number }>("/admin/merchants");
      setMerchants(data.merchants);
    } catch (err) {
      setError("Failed to load merchants");
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-gb-accent" />
      </div>
    );
  }

  if (!authorized) return null;

  const formatXMR = (xmr: string) => {
    const num = parseFloat(xmr);
    return num > 0 ? num.toFixed(4) : "0";
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Shield className="w-7 h-7 text-gb-warning" />
        <div>
          <h1 className="font-heading text-2xl font-bold text-gb-text-primary">
            Instance Admin
          </h1>
          <p className="text-sm text-gb-text-secondary">
            Operator panel — {health?.version || ""}
          </p>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-gb bg-gb-error/10 border border-gb-error/30 text-gb-error text-sm">
          {error}
        </div>
      )}

      {/* System Health */}
      {health && (
        <div className="gb-card space-y-4">
          <h2 className="font-heading text-lg font-semibold text-gb-text-primary flex items-center gap-2">
            <Heart className="w-5 h-5 text-gb-success" />
            System Health
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="flex items-center gap-3 p-3 rounded-gb bg-gb-bg border border-gb-border">
              <StatusDot ok={health.database?.connected === true} />
              <div>
                <p className="text-sm font-medium text-gb-text-primary">Database</p>
                <p className="text-xs text-gb-text-secondary">
                  {health.database?.connected ? "Connected" : "Down"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 rounded-gb bg-gb-bg border border-gb-border">
              <StatusDot ok={health.redis?.connected === true} />
              <div>
                <p className="text-sm font-medium text-gb-text-primary">Redis</p>
                <p className="text-xs text-gb-text-secondary">
                  {health.redis?.connected
                    ? `Mem: ${health.redis.used_memory_human}`
                    : "Down"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 rounded-gb bg-gb-bg border border-gb-border">
              <StatusDot ok={health.wallet_rpc?.connected === true} />
              <div>
                <p className="text-sm font-medium text-gb-text-primary">Wallet RPC</p>
                <p className="text-xs text-gb-text-secondary">
                  {health.wallet_rpc?.connected
                    ? `Height: ${health.wallet_rpc.height}`
                    : "Down"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 rounded-gb bg-gb-bg border border-gb-border">
              <StatusDot ok={Number(health.detection?.blocks_behind || 99) < 5} />
              <div>
                <p className="text-sm font-medium text-gb-text-primary">Detection</p>
                <p className="text-xs text-gb-text-secondary">
                  {health.detection?.blocks_behind === 0
                    ? "Synced"
                    : `${health.detection?.blocks_behind} blocks behind`}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Global Stats */}
      {stats && (
        <div className="gb-card space-y-4">
          <h2 className="font-heading text-lg font-semibold text-gb-text-primary flex items-center gap-2">
            <Database className="w-5 h-5 text-gb-accent" />
            Global Statistics
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
            <div>
              <p className="text-xs text-gb-text-secondary uppercase">Merchants</p>
              <p className="text-2xl font-bold font-mono text-gb-text-primary">{stats.merchants_active}</p>
              <p className="text-xs text-gb-text-secondary">{stats.merchants_total} total</p>
            </div>
            <div>
              <p className="text-xs text-gb-text-secondary uppercase">Invoices</p>
              <p className="text-2xl font-bold font-mono text-gb-text-primary">{stats.invoices_total}</p>
              <p className="text-xs text-gb-success">{stats.invoices_paid} paid</p>
            </div>
            <div>
              <p className="text-xs text-gb-text-secondary uppercase">Payments</p>
              <p className="text-2xl font-bold font-mono text-gb-text-primary">{stats.payments_total}</p>
              <p className="text-xs text-gb-success">{stats.payments_confirmed} confirmed</p>
            </div>
            <div>
              <p className="text-xs text-gb-text-secondary uppercase">Revenue (XMR)</p>
              <p className="text-2xl font-bold font-mono text-gb-accent">{formatXMR(stats.total_revenue_xmr)}</p>
              <p className="text-xs text-gb-text-secondary">all confirmed</p>
            </div>
            <div>
              <p className="text-xs text-gb-text-secondary uppercase">Subscriptions</p>
              <p className="text-2xl font-bold font-mono text-gb-text-primary">{stats.subscriptions_active}</p>
              <p className="text-xs text-gb-text-secondary">{stats.subscriptions_trialing} trialing</p>
            </div>
          </div>

          {/* Alerts */}
          {(stats.invoices_pending > 0 || stats.webhook_dlq_unresolved > 0) && (
            <div className="flex flex-wrap gap-3 pt-2">
              {stats.invoices_pending > 0 && (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs bg-gb-warning/15 text-gb-warning border border-gb-warning/30">
                  <AlertTriangle className="w-3 h-3" />
                  {stats.invoices_pending} invoices pending
                </span>
              )}
              {stats.webhook_dlq_unresolved > 0 && (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs bg-gb-error/15 text-gb-error border border-gb-error/30">
                  <AlertTriangle className="w-3 h-3" />
                  {stats.webhook_dlq_unresolved} DLQ unresolved
                </span>
              )}
              {stats.webhook_deliveries_pending > 0 && (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs bg-blue-500/15 text-blue-400 border border-blue-500/30">
                  <Radio className="w-3 h-3" />
                  {stats.webhook_deliveries_pending} webhooks queued
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Merchants Table */}
      <div className="gb-card space-y-4">
        <h2 className="font-heading text-lg font-semibold text-gb-text-primary flex items-center gap-2">
          <Users className="w-5 h-5 text-gb-teal" />
          Merchants ({merchants.length})
        </h2>
        {merchants.length === 0 ? (
          <p className="text-sm text-gb-text-secondary py-4 text-center">No merchants registered</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gb-border">
                  <th className="text-left text-xs text-gb-text-secondary font-medium pb-2 pr-4">Name</th>
                  <th className="text-left text-xs text-gb-text-secondary font-medium pb-2 pr-4">Email</th>
                  <th className="text-center text-xs text-gb-text-secondary font-medium pb-2 pr-4">Invoices</th>
                  <th className="text-center text-xs text-gb-text-secondary font-medium pb-2 pr-4">Subs</th>
                  <th className="text-center text-xs text-gb-text-secondary font-medium pb-2 pr-4">Status</th>
                  <th className="text-right text-xs text-gb-text-secondary font-medium pb-2">Registered</th>
                </tr>
              </thead>
              <tbody>
                {merchants.map((m) => (
                  <tr key={m.id} className="border-b border-gb-border/50 last:border-0">
                    <td className="py-2.5 pr-4">
                      <p className="text-sm font-medium text-gb-text-primary">{m.name}</p>
                      <p className="text-xs font-mono text-gb-text-secondary">{m.id.slice(0, 12)}...</p>
                    </td>
                    <td className="py-2.5 pr-4 text-sm text-gb-text-secondary">{m.email || "—"}</td>
                    <td className="py-2.5 pr-4 text-center text-sm font-mono text-gb-text-primary">{m.invoice_count}</td>
                    <td className="py-2.5 pr-4 text-center text-sm font-mono text-gb-text-primary">{m.subscription_count}</td>
                    <td className="py-2.5 pr-4 text-center">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                        m.is_active
                          ? "bg-gb-success/15 text-gb-success"
                          : "bg-gb-error/15 text-gb-error"
                      }`}>
                        {m.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td className="py-2.5 text-right text-xs text-gb-text-secondary">
                      {new Date(m.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
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
