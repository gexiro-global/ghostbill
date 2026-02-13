"use client";

import { useEffect, useState, useCallback } from "react";
import { Settings, Save, AlertTriangle, Loader2, AlertCircle } from "lucide-react";
import { api, removeApiKey } from "@/lib/api";
import { Merchant } from "@/lib/types";
import { useToast } from "@/components/Toast";

export default function SettingsPage() {
  const { toast } = useToast();
  const [merchant, setMerchant] = useState<Merchant | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Name editing
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);

  // Danger zone
  const [showDelete, setShowDelete] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [deleting, setDeleting] = useState(false);

  const fetchMerchant = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.get<Merchant>("/merchants/me");
      setMerchant(data);
      setName(data.name);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMerchant();
  }, [fetchMerchant]);

  const handleSaveName = async () => {
    if (!name.trim()) return;
    try {
      setSaving(true);
      const data = await api.patch<Merchant>("/merchants/me", {
        name: name.trim(),
      });
      setMerchant(data);
      toast("success", "Merchant name updated");
    } catch (err: unknown) {
      toast("error", err instanceof Error ? err.message : "Failed to update name");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (deleteConfirmText !== "DELETE") return;
    try {
      setDeleting(true);
      await api.delete("/merchants/me");
      removeApiKey();
      toast("success", "Account deleted");
      window.location.href = "/login";
    } catch (err: unknown) {
      toast("error", err instanceof Error ? err.message : "Failed to delete account");
      setDeleting(false);
    }
  };

  const nameChanged = name.trim() !== (merchant?.name || "");

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="w-6 h-6 text-gb-accent animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 text-gb-error py-12">
        <AlertCircle className="w-5 h-5" />
        <span>{error}</span>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-heading font-bold text-gb-text-primary">
          Settings
        </h1>
        <p className="text-gb-text-secondary mt-1">
          Manage your merchant account settings.
        </p>
      </div>

      {/* Merchant Info */}
      <div className="gb-card">
        <div className="flex items-center gap-3 mb-6">
          <Settings className="w-5 h-5 text-gb-accent" />
          <h2 className="text-lg font-heading font-semibold text-gb-text-primary">
            Merchant Profile
          </h2>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm text-gb-text-secondary mb-1.5">
              Merchant Name
            </label>
            <div className="flex gap-3">
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your business name"
                className="gb-input flex-1 text-sm"
              />
              <button
                onClick={handleSaveName}
                disabled={saving || !nameChanged || !name.trim()}
                className="gb-btn-primary !px-4 !py-2 text-sm flex items-center gap-2"
              >
                {saving ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Save className="w-4 h-4" />
                )}
                Save
              </button>
            </div>
          </div>

          <div>
            <label className="block text-sm text-gb-text-secondary mb-1.5">
              Merchant ID
            </label>
            <div className="bg-gb-bg border border-gb-border rounded-gb px-4 py-2.5">
              <code className="font-mono text-sm text-gb-text-secondary">
                {merchant?.id}
              </code>
            </div>
          </div>

          <div>
            <label className="block text-sm text-gb-text-secondary mb-1.5">
              Member Since
            </label>
            <div className="bg-gb-bg border border-gb-border rounded-gb px-4 py-2.5">
              <span className="text-sm text-gb-text-secondary">
                {merchant?.created_at
                  ? new Date(merchant.created_at).toLocaleDateString("en-US", {
                      year: "numeric",
                      month: "long",
                      day: "numeric",
                    })
                  : "—"}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Danger Zone */}
      <div className="gb-card !border-gb-error/30">
        <div className="flex items-center gap-3 mb-4">
          <AlertTriangle className="w-5 h-5 text-gb-error" />
          <h2 className="text-lg font-heading font-semibold text-gb-error">
            Danger Zone
          </h2>
        </div>

        <p className="text-sm text-gb-text-secondary mb-4">
          Permanently delete your merchant account, all API keys, invoices, and
          payment records. This action cannot be undone.
        </p>

        {!showDelete ? (
          <button
            onClick={() => setShowDelete(true)}
            className="px-4 py-2 text-sm font-medium rounded-gb border border-gb-error/50 text-gb-error hover:bg-gb-error/10 transition-colors"
          >
            Delete Account
          </button>
        ) : (
          <div className="bg-gb-error/5 border border-gb-error/20 rounded-gb p-4 space-y-3">
            <p className="text-sm text-gb-text-primary font-medium">
              Type <code className="font-mono text-gb-error">DELETE</code> to
              confirm:
            </p>
            <input
              type="text"
              value={deleteConfirmText}
              onChange={(e) => setDeleteConfirmText(e.target.value)}
              placeholder="DELETE"
              className="gb-input w-full text-sm font-mono !border-gb-error/30 focus:!border-gb-error focus:!ring-gb-error"
              autoFocus
            />
            <div className="flex gap-3">
              <button
                onClick={() => {
                  setShowDelete(false);
                  setDeleteConfirmText("");
                }}
                className="gb-btn-secondary !px-4 !py-2 text-sm"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting || deleteConfirmText !== "DELETE"}
                className={`px-4 py-2 text-sm font-medium rounded-gb text-white transition-colors flex items-center gap-2 ${
                  deleteConfirmText === "DELETE"
                    ? "bg-gb-error hover:bg-gb-error/80"
                    : "bg-gb-error/30 cursor-not-allowed"
                }`}
              >
                {deleting && <Loader2 className="w-4 h-4 animate-spin" />}
                Permanently Delete
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
