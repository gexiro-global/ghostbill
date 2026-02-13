"use client";
import { useState, useEffect } from "react";
import { ArrowLeft, Loader2, Zap } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Price, Invoice } from "@/lib/types";

const EXPIRY_OPTIONS = [
  { value: "900", label: "15 minutes" },
  { value: "1800", label: "30 minutes" },
  { value: "3600", label: "1 hour" },
  { value: "7200", label: "2 hours" },
  { value: "14400", label: "4 hours" },
  { value: "43200", label: "12 hours" },
  { value: "86400", label: "24 hours" },
];

const PICONERO = BigInt("1000000000000");

export default function NewInvoicePage() {
  const router = useRouter();
  const [mode, setMode] = useState<"xmr" | "fiat">("xmr");
  const [amountXmr, setAmountXmr] = useState("");
  const [fiatAmount, setFiatAmount] = useState("");
  const [fiatCurrency, setFiatCurrency] = useState("USD");
  const [description, setDescription] = useState("");
  const [externalId, setExternalId] = useState("");
  const [expirySeconds, setExpirySeconds] = useState("3600");
  const [price, setPrice] = useState<Price | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch current price for live conversion
  useEffect(() => {
    api
      .get<Price>("/price")
      .then(setPrice)
      .catch(() => {});
  }, []);

  // Convert XMR string to atomic (piconero) string
  function xmrToAtomic(xmr: string): string {
    try {
      const parts = xmr.split(".");
      const whole = parts[0] || "0";
      const frac = (parts[1] || "").padEnd(12, "0").slice(0, 12);
      const atomic = BigInt(whole) * PICONERO + BigInt(frac);
      return atomic.toString();
    } catch {
      return "0";
    }
  }

  // Live preview: estimate opposite amount
  const previewFiat = (() => {
    if (mode !== "xmr" || !amountXmr || !price) return null;
    const xmr = parseFloat(amountXmr);
    if (isNaN(xmr) || xmr <= 0) return null;
    const rate = fiatCurrency === "EUR" ? price.eur : price.usd;
    return (xmr * rate).toFixed(2);
  })();

  const previewXmr = (() => {
    if (mode !== "fiat" || !fiatAmount || !price) return null;
    const fiat = parseFloat(fiatAmount);
    if (isNaN(fiat) || fiat <= 0) return null;
    const rate = fiatCurrency === "EUR" ? price.eur : price.usd;
    if (rate <= 0) return null;
    return (fiat / rate).toFixed(6);
  })();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      // Build request body based on mode
      const body: Record<string, unknown> = {
        expiry_minutes: Math.floor(parseInt(expirySeconds) / 60),
      };

      if (description.trim()) body.description = description.trim();
      if (externalId.trim()) body.external_id = externalId.trim();

      if (mode === "xmr") {
        const atomic = xmrToAtomic(amountXmr);
        if (atomic === "0" || BigInt(atomic) <= BigInt(0)) {
          setError("Amount must be greater than 0");
          setSubmitting(false);
          return;
        }
        body.amount_atomic = atomic;
      } else {
        const fiat = parseFloat(fiatAmount);
        if (isNaN(fiat) || fiat <= 0) {
          setError("Fiat amount must be greater than 0");
          setSubmitting(false);
          return;
        }
        body.fiat_amount = fiat;
        body.fiat_currency = fiatCurrency;
      }

      const invoice = await api.post<Invoice>("/invoices", body);
      router.push(`/dashboard/invoices/${invoice.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create invoice");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link
          href="/dashboard/invoices"
          className="p-2 rounded-gb border border-gb-border text-gb-text-secondary hover:text-gb-text-primary hover:border-gb-accent transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <div>
          <h1 className="font-heading text-2xl font-bold text-gb-text-primary">
            Create Invoice
          </h1>
          <p className="text-gb-text-secondary text-sm mt-1">
            Generate a new payment request
          </p>
        </div>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="gb-card space-y-6">
        {/* Amount mode toggle */}
        <div>
          <label className="block text-sm font-medium text-gb-text-secondary mb-2">
            Amount Type
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setMode("xmr")}
              className={`px-4 py-2 rounded-gb text-sm font-medium transition-colors ${
                mode === "xmr"
                  ? "bg-gb-accent text-white"
                  : "bg-gb-border/30 text-gb-text-secondary hover:text-gb-text-primary"
              }`}
            >
              XMR Amount
            </button>
            <button
              type="button"
              onClick={() => setMode("fiat")}
              className={`px-4 py-2 rounded-gb text-sm font-medium transition-colors ${
                mode === "fiat"
                  ? "bg-gb-accent text-white"
                  : "bg-gb-border/30 text-gb-text-secondary hover:text-gb-text-primary"
              }`}
            >
              Fiat Amount
            </button>
          </div>
        </div>

        {/* XMR amount */}
        {mode === "xmr" && (
          <div>
            <label className="block text-sm font-medium text-gb-text-secondary mb-2">
              Amount (XMR)
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
                ≈ {fiatCurrency === "EUR" ? "€" : "$"}{previewFiat} {fiatCurrency}
                {price?.stale && " (price may be outdated)"}
              </p>
            )}
          </div>
        )}

        {/* Fiat amount */}
        {mode === "fiat" && (
          <div>
            <label className="block text-sm font-medium text-gb-text-secondary mb-2">
              Fiat Amount
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={fiatAmount}
                onChange={(e) => setFiatAmount(e.target.value)}
                placeholder="49.99"
                className="gb-input font-mono flex-1"
                required
              />
              <select
                value={fiatCurrency}
                onChange={(e) => setFiatCurrency(e.target.value)}
                className="gb-input w-24 appearance-none cursor-pointer"
              >
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
              </select>
            </div>
            {previewXmr && (
              <p className="text-xs text-gb-text-secondary mt-1.5 flex items-center gap-1">
                <Zap className="w-3 h-3 text-gb-accent" />
                ≈ {previewXmr} XMR
                {price?.stale && " (price may be outdated)"}
              </p>
            )}
          </div>
        )}

        {/* Description */}
        <div>
          <label className="block text-sm font-medium text-gb-text-secondary mb-2">
            Description
            <span className="text-gb-text-secondary/50 ml-1">(optional)</span>
          </label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Order #1234, subscription renewal, etc."
            className="gb-input w-full"
          />
        </div>

        {/* External ID */}
        <div>
          <label className="block text-sm font-medium text-gb-text-secondary mb-2">
            External ID
            <span className="text-gb-text-secondary/50 ml-1">(optional)</span>
          </label>
          <input
            type="text"
            value={externalId}
            onChange={(e) => setExternalId(e.target.value)}
            placeholder="Your system's order/reference ID"
            className="gb-input w-full font-mono"
          />
        </div>

        {/* Expiry */}
        <div>
          <label className="block text-sm font-medium text-gb-text-secondary mb-2">
            Expires In
          </label>
          <select
            value={expirySeconds}
            onChange={(e) => setExpirySeconds(e.target.value)}
            className="gb-input w-full appearance-none cursor-pointer"
          >
            {EXPIRY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
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
            disabled={submitting}
            className="gb-btn-primary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Zap className="w-4 h-4" />
            )}
            {submitting ? "Creating..." : "Create Invoice"}
          </button>
          <Link
            href="/dashboard/invoices"
            className="gb-btn-secondary"
          >
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
