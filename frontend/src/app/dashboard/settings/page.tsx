"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Settings,
  Save,
  AlertTriangle,
  Loader2,
  AlertCircle,
  Plus,
  Trash2,
  CreditCard,
} from "lucide-react";
import { api, removeApiKey } from "@/lib/api";
import { Merchant, PrepayPlan } from "@/lib/types";
import { useToast } from "@/components/Toast";

export default function SettingsPage() {
  const { toast } = useToast();
  const [merchant, setMerchant] = useState<Merchant | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Name editing
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);

  // Prepay plans
  const [plans, setPlans] = useState<PrepayPlan[]>([]);
  const [newPeriods, setNewPeriods] = useState("");
  const [newDiscount, setNewDiscount] = useState("");
  const [savingPlans, setSavingPlans] = useState(false);
  const [plansChanged, setPlansChanged] = useState(false);

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
      setPlans(data.prepay_plans || []);
      setPlansChanged(false);
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

  const handleAddPlan = () => {
    const periods = parseInt(newPeriods);
    const discount = parseInt(newDiscount) || 0;
    if (isNaN(periods) || periods < 1 || periods > 36) {
      toast("error", "Periods must be 1-36");
      return;
    }
    if (discount < 0 || discount > 99) {
      toast("error", "Discount must be 0-99%");
      return;
    }
    if (plans.some((p) => p.periods === periods)) {
      toast("error", `Plan for ${periods} periods already exists`);
      return;
    }
    if (plans.length >= 10) {
      toast("error", "Maximum 10 prepay plans allowed");
      return;
    }
    const updated = [...plans, { periods, discount_pct: discount }].sort(
      (a, b) => a.periods - b.periods
    );
    setPlans(updated);
    setPlansChanged(true);
    setNewPeriods("");
    setNewDiscount("");
  };

  const handleRemovePlan = (periods: number) => {
    setPlans(plans.filter((p) => p.periods !== periods));
    setPlansChanged(true);
  };

  const handleSavePlans = async () => {
    try {
      setSavingPlans(true);
      const data = await api.patch<Merchant>("/merchants/me", {
        prepay_plans: plans.length > 0 ? plans : null,
      });
      setMerchant(data);
      setPlans(data.prepay_plans || []);
      setPlansChanged(false);
      toast("success", "Prepay plans updated");
    } catch (err: unknown) {
      toast("error", err instanceof Error ? err.message : "Failed to update plans");
    } finally {
      setSavingPlans(false);
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
                  : "\u2014"}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Prepay Plans */}
      <div className="gb-card">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <CreditCard className="w-5 h-5 text-gb-accent" />
            <h2 className="text-lg font-heading font-semibold text-gb-text-primary">
              Prepay Plans
            </h2>
          </div>
          {plansChanged && (
            <button
              onClick={handleSavePlans}
              disabled={savingPlans}
              className="gb-btn-primary !px-4 !py-2 text-sm flex items-center gap-2"
            >
              {savingPlans ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Save className="w-4 h-4" />
              )}
              Save Plans
            </button>
          )}
        </div>

        <p className="text-sm text-gb-text-secondary mb-4">
          Configure prepay options for subscribers. Each plan lets customers pay
          multiple periods upfront with an optional discount.
        </p>

        {/* Current plans */}
        {plans.length > 0 && (
          <div className="space-y-2 mb-4">
            {plans.map((plan) => (
              <div
                key={plan.periods}
                className="flex items-center justify-between p-3 rounded-gb border border-gb-border bg-gb-bg"
              >
                <div className="flex items-center gap-4">
                  <span className="text-sm font-medium text-gb-text-primary">
                    {plan.periods} period{plan.periods > 1 ? "s" : ""}
                  </span>
                  {plan.discount_pct > 0 ? (
                    <span className="text-xs font-medium text-gb-success bg-gb-success/10 px-2 py-0.5 rounded-full">
                      {plan.discount_pct}% discount
                    </span>
                  ) : (
                    <span className="text-xs text-gb-text-secondary">
                      No discount
                    </span>
                  )}
                </div>
                <button
                  onClick={() => handleRemovePlan(plan.periods)}
                  className="text-gb-text-secondary hover:text-gb-error transition-colors p-1"
                  title="Remove plan"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}

        {plans.length === 0 && (
          <p className="text-sm text-gb-text-secondary/60 py-4 text-center mb-4">
            No prepay plans configured. Subscribers cannot prepay.
          </p>
        )}

        {/* Add new plan */}
        {plans.length < 10 && (
          <div className="flex items-end gap-3">
            <div className="flex-1">
              <label className="block text-xs text-gb-text-secondary mb-1">
                Periods (1-36)
              </label>
              <input
                type="number"
                min="1"
                max="36"
                value={newPeriods}
                onChange={(e) => setNewPeriods(e.target.value)}
                placeholder="e.g. 3"
                className="gb-input w-full text-sm font-mono"
              />
            </div>
            <div className="flex-1">
              <label className="block text-xs text-gb-text-secondary mb-1">
                Discount % (0-99)
              </label>
              <input
                type="number"
                min="0"
                max="99"
                value={newDiscount}
                onChange={(e) => setNewDiscount(e.target.value)}
                placeholder="e.g. 10"
                className="gb-input w-full text-sm font-mono"
              />
            </div>
            <button
              onClick={handleAddPlan}
              disabled={!newPeriods}
              className="gb-btn-secondary !px-4 !py-2 text-sm flex items-center gap-2 shrink-0"
            >
              <Plus className="w-4 h-4" />
              Add
            </button>
          </div>
        )}
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
