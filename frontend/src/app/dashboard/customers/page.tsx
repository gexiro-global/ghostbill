"use client";
import { useEffect, useState, useCallback } from "react";
import { Plus, Users, X, Loader2, Pencil } from "lucide-react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import Pagination from "@/components/Pagination";
import EmptyState from "@/components/EmptyState";
import type { Customer, CursorResponse } from "@/lib/types";

const LIMIT = 20;

interface CustomerFormData {
  external_id: string;
  email: string;
  metadata: string;
}

const emptyForm: CustomerFormData = { external_id: "", email: "", metadata: "" };

export default function CustomersPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const [prevCursors, setPrevCursors] = useState<(string | null)[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<CustomerFormData>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const fetchCustomers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set("limit", LIMIT.toString());
      if (cursor) params.set("starting_after", cursor);
      const data = await api.get<CursorResponse<Customer>>(`/customers?${params}`);
      setCustomers(data.data);
      setHasMore(data.has_more);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load customers");
    } finally {
      setLoading(false);
    }
  }, [cursor]);

  useEffect(() => {
    fetchCustomers();
  }, [fetchCustomers]);

  const handleNext = () => {
    if (customers.length === 0 || !hasMore) return;
    setPrevCursors([...prevCursors, cursor]);
    setCursor(customers[customers.length - 1].id);
  };

  const handlePrev = () => {
    if (prevCursors.length === 0) return;
    const prev = prevCursors[prevCursors.length - 1];
    setPrevCursors(prevCursors.slice(0, -1));
    setCursor(prev);
  };

  // Client-side filter
  const filtered = search
    ? customers.filter(
        (c) =>
          (c.external_id || "").toLowerCase().includes(search.toLowerCase()) ||
          (c.email || "").toLowerCase().includes(search.toLowerCase())
      )
    : customers;

  function openCreate() {
    setEditingId(null);
    setForm(emptyForm);
    setFormError(null);
    setModalOpen(true);
  }

  function openEdit(c: Customer) {
    setEditingId(c.id);
    setForm({
      external_id: c.external_id || "",
      email: c.email || "",
      metadata: Object.keys(c.metadata).length > 0 ? JSON.stringify(c.metadata, null, 2) : "",
    });
    setFormError(null);
    setModalOpen(true);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setSubmitting(true);

    try {
      let parsedMeta: Record<string, unknown> = {};
      if (form.metadata.trim()) {
        try {
          parsedMeta = JSON.parse(form.metadata);
        } catch {
          setFormError("Metadata must be valid JSON");
          setSubmitting(false);
          return;
        }
      }

      const body: Record<string, unknown> = {
        external_id: form.external_id.trim() || null,
        email: form.email.trim() || null,
        metadata: parsedMeta,
      };

      if (editingId) {
        await api.patch(`/customers/${editingId}`, body);
      } else {
        await api.post("/customers", body);
      }

      setModalOpen(false);
      fetchCustomers();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to save customer");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-2xl font-bold text-gb-text-primary">
            Customers
          </h1>
        </div>
        <button onClick={openCreate} className="gb-btn-primary flex items-center gap-2">
          <Plus className="w-4 h-4" />
          New Customer
        </button>
      </div>

      {/* Search */}
      <div className="flex items-center gap-4">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter by external ID or email..."
          className="gb-input text-sm w-full max-w-sm"
        />
      </div>

      {/* Error */}
      {error && (
        <div className="gb-card border-gb-error/50 text-gb-error text-sm">{error}</div>
      )}

      {/* Table */}
      <div className="gb-card">
        {loading ? (
          <div className="space-y-4">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-12 bg-gb-border/20 rounded animate-pulse" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={Users}
            title={search ? "No customers match this filter" : "No customers yet"}
            description={
              search
                ? "Try a different search term"
                : "Create your first customer to start managing subscriptions."
            }
            action={
              !search ? (
                <button
                  onClick={openCreate}
                  className="gb-btn-primary inline-flex items-center gap-2"
                >
                  <Plus className="w-4 h-4" />
                  Create Customer
                </button>
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
                      External ID
                    </th>
                    <th className="text-left text-xs text-gb-text-secondary font-medium pb-3 pr-4">
                      Email
                    </th>
                    <th className="text-left text-xs text-gb-text-secondary font-medium pb-3 pr-4 hidden md:table-cell">
                      ID
                    </th>
                    <th className="text-right text-xs text-gb-text-secondary font-medium pb-3">
                      Created
                    </th>
                    <th className="text-right text-xs text-gb-text-secondary font-medium pb-3 w-10">
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((cust) => (
                    <tr
                      key={cust.id}
                      className="border-b border-gb-border/50 last:border-0 hover:bg-gb-border/10 transition-colors"
                    >
                      <td className="py-3 pr-4">
                        <span className="font-mono text-sm text-gb-text-primary">
                          {cust.external_id || "\u2014"}
                        </span>
                      </td>
                      <td className="py-3 pr-4">
                        <span className="text-sm text-gb-text-primary">
                          {cust.email || "\u2014"}
                        </span>
                      </td>
                      <td className="py-3 pr-4 hidden md:table-cell">
                        <span className="font-mono text-xs text-gb-text-secondary">
                          {cust.id.slice(0, 8)}...
                        </span>
                      </td>
                      <td className="py-3 text-right">
                        <span className="text-sm text-gb-text-secondary">
                          {formatDate(cust.created_at)}
                        </span>
                      </td>
                      <td className="py-3 text-right">
                        <button
                          onClick={() => openEdit(cust)}
                          className="p-1.5 rounded text-gb-text-secondary hover:text-gb-accent hover:bg-gb-accent/10 transition-colors"
                          title="Edit customer"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
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

      {/* Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setModalOpen(false)}
          />
          <div className="relative bg-gb-sidebar border border-gb-border rounded-gb p-6 w-full max-w-md mx-4 space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="font-heading text-lg font-semibold text-gb-text-primary">
                {editingId ? "Edit Customer" : "New Customer"}
              </h2>
              <button
                onClick={() => setModalOpen(false)}
                className="p-1 rounded text-gb-text-secondary hover:text-gb-text-primary transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gb-text-secondary mb-1.5">
                  External ID
                  <span className="text-gb-text-secondary/50 ml-1">(optional)</span>
                </label>
                <input
                  type="text"
                  value={form.external_id}
                  onChange={(e) => setForm({ ...form, external_id: e.target.value })}
                  placeholder="your-system-customer-id"
                  className="gb-input w-full font-mono"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gb-text-secondary mb-1.5">
                  Email
                  <span className="text-gb-text-secondary/50 ml-1">(optional)</span>
                </label>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  placeholder="customer@example.com"
                  className="gb-input w-full"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gb-text-secondary mb-1.5">
                  Metadata
                  <span className="text-gb-text-secondary/50 ml-1">(optional JSON)</span>
                </label>
                <textarea
                  value={form.metadata}
                  onChange={(e) => setForm({ ...form, metadata: e.target.value })}
                  placeholder='{"plan": "premium"}'
                  rows={3}
                  className="gb-input w-full font-mono text-xs resize-none"
                />
              </div>

              {formError && (
                <div className="p-3 rounded-gb bg-gb-error/10 border border-gb-error/30 text-gb-error text-sm">
                  {formError}
                </div>
              )}

              <div className="flex items-center gap-3 pt-1">
                <button
                  type="submit"
                  disabled={submitting}
                  className="gb-btn-primary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
                  {submitting
                    ? "Saving..."
                    : editingId
                    ? "Update Customer"
                    : "Create Customer"}
                </button>
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="gb-btn-secondary"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
