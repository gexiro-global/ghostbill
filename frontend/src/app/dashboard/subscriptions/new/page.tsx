"use client";
import { useState, useEffect } from "react";
import { ArrowLeft, Loader2, Zap } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Customer, CustomerListResponse, Price, Subscription } from "@/lib/types";

const INTERVAL_PRESETS = [
  { value: 7, label: "Weekly (7 days)" },
  { value: 14, label: "Bi-weekly (14 days)" },
  { value: 30, label: "Monthly (30 days)" },
  { value: 90, label: "Quarterly (90 days)" },
  { value: 365, label: "Yearly (365 days)" },
  { value: 0, label: "Custom" },
];

export default function NewSubscriptionPage() {
  const router = useRouter();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [price, setPrice] = useState<Price | null>(null);

  const [customerId, setCustomerId] = useState("");
  const [amountXmr, setAmountXmr] = useState("");
  const [intervalPreset, setIntervalPreset] = useState(30);
  const [customInterval, setCustomInterval] = useState("");
  const [graceSoft, setGraceSoft] = useState("3");
  const [graceHard, setGraceHard] = useState("7");
  const [metadata, setMetadata] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const intervalDays = intervalPreset === 0 ? parseInt(customInterval) || 0 : intervalPreset;

  const previewFiat = (() => {
    if (!amountXmr || !price) return null;
    const xmr = parseFloat(amountXmr);
    if (isNaN(xmr) || xmr <= 0) return null;
    return (xmr * price.usd).toFixed(2);
  })();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!customerId) {
      setError("Please select a customer");
      return;
    }
    const xmr = parseFloat(amountXmr);
    if (isNaN(xmr) || xmr <= 0) {
      setError("Amount must be greater than 0");
      return;
    }
    if (intervalDays < 1) {
      setError("Interval must be at least 1 day");
      return;
    }
    const soft = parseInt(graceSoft) || 3;
    const hard = parseInt(graceHard) || 7;
    if (hard < soft) {
      setError("Hard grace period must be ≥ soft grace period");
      return;
    }

    let parsedMeta: Record<string, unknown> = {};
    if (metadata.trim()) {
      try {
        parsedMeta = JSON.parse(metadata);
      } catch {
        setError("Metadata must be valid JSON");
        return;
      }
    }

    setSubmitting(true);
    try {
      const body: Record<string, unknown> = {
        customer_id: customerId,
        amount_xmr: amountXmr,
        interval_days: intervalDays,
        grace_days_soft: soft,
        grace_days_hard: hard,
        metadata: parsedMeta,
      };

      const sub = await api.post<Subscription>("/subscriptions", body);
      router.push(`/dashboard/subscriptions/${sub.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create subscription");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link
          href="/dashboard/subscriptions"
          className="p-2 rounded-gb border border-gb-border text-gb-text-secondary hover:text-gb-text-primary hover:border-gb-accent transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <div>
          <h1 className="font-heading text-2xl font-bold text-gb-text-primary">
            Create Subscription
          </h1>
          <p className="text-gb-text-secondary text-sm mt-1">
            Set up recurring billing for a customer
          </p>
        </div>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="gb-card space-y-6">
        {/* Customer select */}
        <div>
          <label className="block text-sm font-medium text-gb-text-secondary mb-2">
            Customer
          </label>
          {customers.length === 0 ? (
            <div className="p-3 rounded-gb bg-gb-warning/10 border border-gb-warning/30 text-gb-warning text-sm">
              No customers found.{" "}
              <Link href="/dashboard/customers" className="underline">
                Create a customer first
              </Link>
              .
            </div>
          ) : (
            <select
              value={customerId}
              onChange={(e) => setCustomerId(e.target.value)}
              className="gb-input w-full appearance-none cursor-pointer"
              required
            >
              <option value="">Select a customer...</option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.external_id || c.email || c.id.slice(0, 12) + "..."}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Amount */}
        <div>
          <label className="block text-sm font-medium text-gb-text-secondary mb-2">
            Amount per Period (XMR)
          </label>
          <input
            type="text"
            value={amountXmr}
            onChange={(e) => setAmountXmr(e.target.value)}
            placeholder="0.5"
            className="gb-input font-mono w-full"
            required
          />
          {previewFiat && (
            <p className="text-xs text-gb-text-secondary mt-1.5 flex items-center gap-1">
              <Zap className="w-3 h-3 text-gb-accent" />
              ≈ ${previewFiat} USD per period
              {price?.stale && " (price may be outdated)"}
            </p>
          )}
          <p className="text-xs text-gb-text-secondary/60 mt-1">
            Price is locked at invoice creation, not subscription creation.
          </p>
        </div>

        {/* Interval */}
        <div>
          <label className="block text-sm font-medium text-gb-text-secondary mb-2">
            Billing Interval
          </label>
          <div className="flex flex-wrap gap-2">
            {INTERVAL_PRESETS.map((preset) => (
              <button
                key={preset.value}
                type="button"
                onClick={() => setIntervalPreset(preset.value)}
                className={`px-3 py-1.5 rounded-gb text-sm font-medium transition-colors ${
                  intervalPreset === preset.value
                    ? "bg-gb-accent text-white"
                    : "bg-gb-border/30 text-gb-text-secondary hover:text-gb-text-primary"
                }`}
              >
                {preset.label}
              </button>
            ))}
          </div>
          {intervalPreset === 0 && (
            <input
              type="number"
              value={customInterval}
              onChange={(e) => setCustomInterval(e.target.value)}
              placeholder="Number of days"
              min="1"
              className="gb-input w-full mt-3 font-mono"
              required
            />
          )}
        </div>

        {/* Grace periods */}
        <div>
          <label className="block text-sm font-medium text-gb-text-secondary mb-2">
            Grace Periods (days)
          </label>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gb-text-secondary/70 mb-1">
                Soft (→ past_due)
              </label>
              <input
                type="number"
                value={graceSoft}
                onChange={(e) => setGraceSoft(e.target.value)}
                min="0"
                className="gb-input w-full font-mono"
              />
            </div>
            <div>
              <label className="block text-xs text-gb-text-secondary/70 mb-1">
                Hard (→ expired)
              </label>
              <input
                type="number"
                value={graceHard}
                onChange={(e) => setGraceHard(e.target.value)}
                min="0"
                className="gb-input w-full font-mono"
              />
            </div>
          </div>
          <p className="text-xs text-gb-text-secondary/60 mt-1.5">
            Soft: subscription moves to past_due. Hard: subscription is cancelled.
          </p>
        </div>

        {/* Metadata */}
        <div>
          <label className="block text-sm font-medium text-gb-text-secondary mb-2">
            Metadata
            <span className="text-gb-text-secondary/50 ml-1">(optional JSON)</span>
          </label>
          <textarea
            value={metadata}
            onChange={(e) => setMetadata(e.target.value)}
            placeholder='{"plan": "premium", "tier": "gold"}'
            rows={3}
            className="gb-input w-full font-mono text-xs resize-none"
          />
        </div>

        {/* Error */}
        {error && (
          <div className="p-3 rounded-gb bg-gb-error/10 border border-gb-error/30 text-gb-error text-sm">
            {error}
          </div>
        )}

        {/* Submit */}
        <div className="flex items-center gap-4 pt-2">
          <button
            type="submit"
            disabled={submitting || customers.length === 0}
            className="gb-btn-primary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Zap className="w-4 h-4" />
            )}
            {submitting ? "Creating..." : "Create Subscription"}
          </button>
          <Link href="/dashboard/subscriptions" className="gb-btn-secondary">
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
