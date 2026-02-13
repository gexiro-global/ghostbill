"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Key,
  Plus,
  Trash2,
  RefreshCw,
  Eye,
  EyeOff,
  Send,
  RotateCcw,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { api } from "@/lib/api";
import { ApiKey, ApiKeyCreated, ApiKeyListResponse, Merchant, WebhookDelivery, WebhookDeliveryListResponse } from "@/lib/types";
import { formatDate, timeAgo } from "@/lib/format";
import CopyButton from "@/components/CopyButton";
import ConfirmDialog from "@/components/ConfirmDialog";
import JsonViewer from "@/components/JsonViewer";
import { useToast } from "@/components/Toast";
import Pagination from "@/components/Pagination";

export default function DevelopersPage() {
  return (
    <div className="space-y-8">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-heading font-bold text-gb-text-primary">
          Developers
        </h1>
        <p className="text-gb-text-secondary mt-1">
          Manage API keys, webhook configuration and delivery logs.
        </p>
      </div>

      <ApiKeysSection />
      <WebhookConfigSection />
      <WebhookLogSection />
    </div>
  );
}

/* ==========================================================================
   SECTION 1: API KEYS
   ========================================================================== */

function ApiKeysSection() {
  const { toast } = useToast();
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create modal
  const [showCreate, setShowCreate] = useState(false);
  const [createLabel, setCreateLabel] = useState("");
  const [createEnv, setCreateEnv] = useState<"live" | "test">("test");
  const [creating, setCreating] = useState(false);
  const [newKey, setNewKey] = useState<ApiKeyCreated | null>(null);

  // Revoke confirm
  const [revokeTarget, setRevokeTarget] = useState<ApiKey | null>(null);
  const [revoking, setRevoking] = useState(false);

  const fetchKeys = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.get<ApiKeyListResponse>("/api-keys");
      setKeys(data.api_keys);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load API keys");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchKeys();
  }, [fetchKeys]);

  const handleCreate = async () => {
    if (!createLabel.trim()) return;
    try {
      setCreating(true);
      const data = await api.post<ApiKeyCreated>("/api-keys", {
        label: createLabel.trim(),
        environment: createEnv,
      });
      setNewKey(data);
      fetchKeys();
      toast("success", "API key created successfully");
    } catch (err: unknown) {
      toast("error", err instanceof Error ? err.message : "Failed to create key");
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async () => {
    if (!revokeTarget) return;
    try {
      setRevoking(true);
      await api.delete(`/api-keys/${revokeTarget.id}`);
      setRevokeTarget(null);
      fetchKeys();
      toast("success", "API key revoked");
    } catch (err: unknown) {
      toast("error", err instanceof Error ? err.message : "Failed to revoke key");
    } finally {
      setRevoking(false);
    }
  };

  const closeCreateModal = () => {
    setShowCreate(false);
    setCreateLabel("");
    setCreateEnv("test");
    setNewKey(null);
  };

  return (
    <div className="gb-card">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Key className="w-5 h-5 text-gb-accent" />
          <h2 className="text-lg font-heading font-semibold text-gb-text-primary">
            API Keys
          </h2>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="gb-btn-primary !px-4 !py-2 text-sm flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          Create Key
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 text-gb-accent animate-spin" />
        </div>
      ) : error ? (
        <div className="flex items-center gap-2 text-gb-error py-4">
          <AlertCircle className="w-5 h-5" />
          <span className="text-sm">{error}</span>
        </div>
      ) : keys.length === 0 ? (
        <p className="text-gb-text-secondary text-sm py-4">
          No API keys yet. Create one to get started.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gb-text-secondary border-b border-gb-border">
                <th className="pb-3 font-medium">Label</th>
                <th className="pb-3 font-medium">Key Prefix</th>
                <th className="pb-3 font-medium">Environment</th>
                <th className="pb-3 font-medium">Created</th>
                <th className="pb-3 font-medium">Last Used</th>
                <th className="pb-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gb-border">
              {keys.map((k) => (
                <tr key={k.id} className="hover:bg-gb-bg/50">
                  <td className="py-3 text-gb-text-primary font-medium">
                    {k.label || "—"}
                  </td>
                  <td className="py-3 font-mono text-gb-text-secondary">
                    {k.key_prefix}...
                  </td>
                  <td className="py-3">
                    <span
                      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-mono font-medium ${
                        k.environment === "live"
                          ? "bg-gb-success/15 text-gb-success"
                          : "bg-gb-warning/15 text-gb-warning"
                      }`}
                    >
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${
                          k.environment === "live" ? "bg-gb-success" : "bg-gb-warning"
                        }`}
                      />
                      {k.environment.toUpperCase()}
                    </span>
                  </td>
                  <td className="py-3 text-gb-text-secondary">
                    {k.created_at ? timeAgo(k.created_at) : "—"}
                  </td>
                  <td className="py-3 text-gb-text-secondary">
                    {k.last_used_at ? timeAgo(k.last_used_at) : "Never"}
                  </td>
                  <td className="py-3 text-right">
                    <button
                      onClick={() => setRevokeTarget(k)}
                      className="text-gb-text-secondary hover:text-gb-error transition-colors p-1"
                      title="Revoke key"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create Key Modal */}
      {showCreate && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeCreateModal();
          }}
        >
          <div className="bg-gb-card border border-gb-border rounded-gb shadow-2xl w-full max-w-md mx-4 p-6">
            {newKey ? (
              /* One-time key display */
              <>
                <h3 className="text-lg font-heading font-semibold text-gb-text-primary mb-2">
                  API Key Created
                </h3>
                <div className="bg-gb-warning/10 border border-gb-warning/30 rounded-gb p-3 mb-4">
                  <p className="text-sm text-gb-warning font-medium">
                    Copy this key now — it will not be shown again!
                  </p>
                </div>
                <div className="bg-gb-bg border border-gb-border rounded-gb p-4 mb-4">
                  <div className="flex items-center justify-between gap-2">
                    <code className="font-mono text-sm text-gb-accent break-all flex-1">
                      {newKey.key}
                    </code>
                    <CopyButton text={newKey.key} />
                  </div>
                </div>
                <div className="text-sm text-gb-text-secondary space-y-1 mb-6">
                  <p>Label: <span className="text-gb-text-primary">{newKey.label || "—"}</span></p>
                  <p>Environment: <span className={newKey.environment === "live" ? "text-gb-success" : "text-gb-warning"}>{newKey.environment.toUpperCase()}</span></p>
                </div>
                <button onClick={closeCreateModal} className="gb-btn-secondary w-full text-sm !py-2">
                  Done
                </button>
              </>
            ) : (
              /* Create form */
              <>
                <h3 className="text-lg font-heading font-semibold text-gb-text-primary mb-4">
                  Create API Key
                </h3>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm text-gb-text-secondary mb-1.5">
                      Label
                    </label>
                    <input
                      type="text"
                      value={createLabel}
                      onChange={(e) => setCreateLabel(e.target.value)}
                      placeholder="e.g. Production Backend"
                      className="gb-input w-full text-sm"
                      autoFocus
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gb-text-secondary mb-1.5">
                      Environment
                    </label>
                    <div className="flex gap-3">
                      <button
                        onClick={() => setCreateEnv("test")}
                        className={`flex-1 px-4 py-2.5 rounded-gb border text-sm font-medium transition-colors ${
                          createEnv === "test"
                            ? "border-gb-warning bg-gb-warning/10 text-gb-warning"
                            : "border-gb-border text-gb-text-secondary hover:text-gb-text-primary"
                        }`}
                      >
                        TEST
                      </button>
                      <button
                        onClick={() => setCreateEnv("live")}
                        className={`flex-1 px-4 py-2.5 rounded-gb border text-sm font-medium transition-colors ${
                          createEnv === "live"
                            ? "border-gb-success bg-gb-success/10 text-gb-success"
                            : "border-gb-border text-gb-text-secondary hover:text-gb-text-primary"
                        }`}
                      >
                        LIVE
                      </button>
                    </div>
                  </div>
                </div>
                <div className="flex justify-end gap-3 mt-6">
                  <button
                    onClick={closeCreateModal}
                    className="gb-btn-secondary !px-4 !py-2 text-sm"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleCreate}
                    disabled={creating || !createLabel.trim()}
                    className="gb-btn-primary !px-4 !py-2 text-sm flex items-center gap-2"
                  >
                    {creating && <Loader2 className="w-4 h-4 animate-spin" />}
                    Create
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Revoke Confirm */}
      <ConfirmDialog
        open={!!revokeTarget}
        onClose={() => setRevokeTarget(null)}
        onConfirm={handleRevoke}
        title="Revoke API Key"
        message={`Are you sure you want to revoke "${revokeTarget?.label || revokeTarget?.key_prefix}"? Any integrations using this key will stop working immediately.`}
        confirmLabel="Revoke Key"
        destructive
        loading={revoking}
      />
    </div>
  );
}

/* ==========================================================================
   SECTION 2: WEBHOOK CONFIG
   ========================================================================== */

function WebhookConfigSection() {
  const { toast } = useToast();
  const [merchant, setMerchant] = useState<Merchant | null>(null);
  const [loading, setLoading] = useState(true);

  // URL editing
  const [webhookUrl, setWebhookUrl] = useState("");
  const [saving, setSaving] = useState(false);

  // Secret visibility
  const [showSecret, setShowSecret] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [showRegenConfirm, setShowRegenConfirm] = useState(false);

  const fetchMerchant = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.get<Merchant>("/merchants/me");
      setMerchant(data);
      setWebhookUrl(data.webhook_url || "");
    } catch (err: unknown) {
      toast("error", err instanceof Error ? err.message : "Failed to load merchant");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    fetchMerchant();
  }, [fetchMerchant]);

  const handleSaveUrl = async () => {
    try {
      setSaving(true);
      const data = await api.patch<Merchant>("/merchants/me", {
        webhook_url: webhookUrl.trim() || null,
      });
      setMerchant(data);
      toast("success", "Webhook URL saved");
    } catch (err: unknown) {
      toast("error", err instanceof Error ? err.message : "Failed to save webhook URL");
    } finally {
      setSaving(false);
    }
  };

  const handleRegenSecret = async () => {
    try {
      setRegenerating(true);
      const data = await api.post<{ webhook_secret: string }>(
        "/merchants/me/webhook-secret"
      );
      setMerchant((prev) =>
        prev ? { ...prev, webhook_secret: data.webhook_secret } : prev
      );
      setShowRegenConfirm(false);
      setShowSecret(true);
      toast("success", "Webhook secret regenerated");
    } catch (err: unknown) {
      toast("error", err instanceof Error ? err.message : "Failed to regenerate secret");
    } finally {
      setRegenerating(false);
    }
  };

  const maskedSecret = merchant?.webhook_secret
    ? merchant.webhook_secret.slice(0, 8) + "••••••••••••••••"
    : null;

  const urlChanged = webhookUrl.trim() !== (merchant?.webhook_url || "");

  return (
    <div className="gb-card">
      <div className="flex items-center gap-3 mb-6">
        <Send className="w-5 h-5 text-gb-accent" />
        <h2 className="text-lg font-heading font-semibold text-gb-text-primary">
          Webhooks
        </h2>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 text-gb-accent animate-spin" />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Webhook URL */}
          <div>
            <label className="block text-sm text-gb-text-secondary mb-1.5">
              Endpoint URL
            </label>
            <div className="flex gap-3">
              <input
                type="url"
                value={webhookUrl}
                onChange={(e) => setWebhookUrl(e.target.value)}
                placeholder="https://yourapp.com/webhooks/ghostbill"
                className="gb-input flex-1 text-sm font-mono"
              />
              <button
                onClick={handleSaveUrl}
                disabled={saving || !urlChanged}
                className="gb-btn-primary !px-4 !py-2 text-sm flex items-center gap-2"
              >
                {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                Save
              </button>
            </div>
          </div>

          {/* Webhook Secret */}
          <div>
            <label className="block text-sm text-gb-text-secondary mb-1.5">
              Signing Secret
            </label>
            {merchant?.webhook_secret ? (
              <div className="flex items-center gap-3">
                <div className="bg-gb-bg border border-gb-border rounded-gb px-4 py-2.5 flex-1">
                  <code className="font-mono text-sm text-gb-text-primary">
                    {showSecret ? merchant.webhook_secret : maskedSecret}
                  </code>
                </div>
                <button
                  onClick={() => setShowSecret(!showSecret)}
                  className="text-gb-text-secondary hover:text-gb-text-primary transition-colors p-2"
                  title={showSecret ? "Hide" : "Show"}
                >
                  {showSecret ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
                <CopyButton text={merchant.webhook_secret} />
                <button
                  onClick={() => setShowRegenConfirm(true)}
                  className="text-gb-text-secondary hover:text-gb-warning transition-colors p-2"
                  title="Regenerate secret"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-3">
                <p className="text-sm text-gb-text-secondary flex-1">
                  No signing secret configured.
                </p>
                <button
                  onClick={handleRegenSecret}
                  disabled={regenerating}
                  className="gb-btn-secondary !px-4 !py-2 text-sm flex items-center gap-2"
                >
                  {regenerating && <Loader2 className="w-4 h-4 animate-spin" />}
                  Generate Secret
                </button>
              </div>
            )}

            <p className="text-xs text-gb-text-secondary mt-2">
              Use this secret to verify webhook signatures via the{" "}
              <code className="font-mono text-gb-accent">X-GhostBill-Signature</code>{" "}
              header (HMAC-SHA256).
            </p>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={showRegenConfirm}
        onClose={() => setShowRegenConfirm(false)}
        onConfirm={handleRegenSecret}
        title="Regenerate Webhook Secret"
        message="This will invalidate your current signing secret. Any integrations verifying webhook signatures will need to be updated."
        confirmLabel="Regenerate"
        destructive
        loading={regenerating}
      />
    </div>
  );
}

/* ==========================================================================
   SECTION 3: WEBHOOK DELIVERY LOG
   ========================================================================== */

function WebhookLogSection() {
  const { toast } = useToast();
  const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const limit = 20;

  // JSON viewer
  const [viewPayload, setViewPayload] = useState<WebhookDelivery | null>(null);

  // Retry
  const [retryingId, setRetryingId] = useState<string | null>(null);

  const fetchDeliveries = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.get<WebhookDeliveryListResponse>(
        `/webhooks?limit=${limit}&offset=${offset}`
      );
      setDeliveries(data.deliveries);
      setTotal(data.total);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load deliveries");
    } finally {
      setLoading(false);
    }
  }, [offset]);

  useEffect(() => {
    fetchDeliveries();
  }, [fetchDeliveries]);

  const handleRetry = async (id: string) => {
    try {
      setRetryingId(id);
      await api.post(`/webhooks/${id}/retry`);
      toast("success", "Webhook delivery retried");
      fetchDeliveries();
    } catch (err: unknown) {
      toast("error", err instanceof Error ? err.message : "Failed to retry delivery");
    } finally {
      setRetryingId(null);
    }
  };

  const statusColor = (status: number | null) => {
    if (!status) return "text-gb-text-secondary";
    if (status >= 200 && status < 300) return "text-gb-success";
    if (status >= 400) return "text-gb-error";
    return "text-gb-warning";
  };

  return (
    <div className="gb-card">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <RotateCcw className="w-5 h-5 text-gb-accent" />
          <h2 className="text-lg font-heading font-semibold text-gb-text-primary">
            Delivery Log
          </h2>
          {total > 0 && (
            <span className="text-xs text-gb-text-secondary bg-gb-bg px-2 py-0.5 rounded-full">
              {total}
            </span>
          )}
        </div>
        <button
          onClick={fetchDeliveries}
          disabled={loading}
          className="text-gb-text-secondary hover:text-gb-accent transition-colors p-2"
          title="Refresh"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {loading && deliveries.length === 0 ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 text-gb-accent animate-spin" />
        </div>
      ) : error ? (
        <div className="flex items-center gap-2 text-gb-error py-4">
          <AlertCircle className="w-5 h-5" />
          <span className="text-sm">{error}</span>
        </div>
      ) : deliveries.length === 0 ? (
        <p className="text-gb-text-secondary text-sm py-4">
          No webhook deliveries yet. They will appear here once webhooks are triggered.
        </p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gb-text-secondary border-b border-gb-border">
                  <th className="pb-3 font-medium">Event</th>
                  <th className="pb-3 font-medium">Status</th>
                  <th className="pb-3 font-medium">Attempt</th>
                  <th className="pb-3 font-medium">Time</th>
                  <th className="pb-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gb-border">
                {deliveries.map((d) => (
                  <tr key={d.id} className="hover:bg-gb-bg/50">
                    <td className="py-3">
                      <span className="font-mono text-gb-text-primary text-xs">
                        {d.event}
                      </span>
                    </td>
                    <td className="py-3">
                      <span className={`font-mono font-medium ${statusColor(d.response_status)}`}>
                        {d.response_status ?? "—"}
                      </span>
                    </td>
                    <td className="py-3 text-gb-text-secondary">
                      {d.attempt}/{d.max_attempts}
                    </td>
                    <td className="py-3 text-gb-text-secondary">
                      {d.delivered_at ? timeAgo(d.delivered_at) : d.next_retry_at ? `retry ${timeAgo(d.next_retry_at)}` : "pending"}
                    </td>
                    <td className="py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => setViewPayload(d)}
                          className="text-gb-text-secondary hover:text-gb-accent transition-colors p-1"
                          title="View payload"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        {d.response_status !== null &&
                          (d.response_status < 200 || d.response_status >= 300) && (
                            <button
                              onClick={() => handleRetry(d.id)}
                              disabled={retryingId === d.id}
                              className="text-gb-text-secondary hover:text-gb-warning transition-colors p-1"
                              title="Retry delivery"
                            >
                              {retryingId === d.id ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                              ) : (
                                <RotateCcw className="w-4 h-4" />
                              )}
                            </button>
                          )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4">
            <Pagination
              total={total}
              limit={limit}
              offset={offset}
              onPageChange={setOffset}
            />
          </div>
        </>
      )}

      {/* JSON Payload Viewer */}
      <JsonViewer
        open={!!viewPayload}
        onClose={() => setViewPayload(null)}
        title={viewPayload ? `${viewPayload.event} — Payload` : "Payload"}
        data={viewPayload?.payload || null}
      />
    </div>
  );
}
