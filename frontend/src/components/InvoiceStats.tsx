"use client";
import { useState, useEffect } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from "recharts";
import { PieChart as PieIcon } from "lucide-react";
import { api } from "@/lib/api";

interface InvoiceStatsData {
  total: number;
  data: { status: string; count: number }[];
  period_days: number;
}

const STATUS_COLORS: Record<string, string> = {
  paid: "#22c55e",
  pending: "#f59e0b",
  expired: "#6b7280",
  partially_paid: "#3b82f6",
  overpaid: "#a855f7",
  late_paid: "#ef4444",
  cancelled: "#64748b",
};

const STATUS_LABELS: Record<string, string> = {
  paid: "Paid",
  pending: "Pending",
  expired: "Expired",
  partially_paid: "Partial",
  overpaid: "Overpaid",
  late_paid: "Late",
  cancelled: "Cancelled",
};

export default function InvoiceStats() {
  const [data, setData] = useState<InvoiceStatsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<InvoiceStatsData>("/analytics/invoices?period_days=30")
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed"))
      .finally(() => setLoading(false));
  }, []);

  const chartData = (data?.data || []).map((d) => ({
    status: STATUS_LABELS[d.status] || d.status,
    count: d.count,
    color: STATUS_COLORS[d.status] || "#6b7280",
    raw: d.status,
  }));

  return (
    <div className="gb-card">
      <div className="flex items-center gap-2 mb-4">
        <PieIcon className="w-5 h-5 text-gb-accent" />
        <h2 className="font-heading text-lg font-semibold text-gb-text-primary">
          Invoices
        </h2>
        {data && (
          <span className="text-sm text-gb-text-secondary ml-2">
            {data.total} total (last {data.period_days}d)
          </span>
        )}
      </div>

      {loading ? (
        <div className="h-[200px] bg-gb-border/10 rounded animate-pulse" />
      ) : error ? (
        <div className="h-[200px] flex items-center justify-center text-gb-error text-sm">
          {error}
        </div>
      ) : chartData.length === 0 ? (
        <div className="h-[200px] flex items-center justify-center text-gb-text-secondary text-sm">
          No invoices in this period
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={chartData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="#1a1a2e" horizontal={false} />
            <XAxis
              type="number"
              tick={{ fill: "#6b6b8a", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              allowDecimals={false}
            />
            <YAxis
              type="category"
              dataKey="status"
              tick={{ fill: "#8a8aaa", fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              width={70}
            />
            <Tooltip
              contentStyle={{
                background: "#0f0f1a",
                border: "1px solid #1a1a2e",
                borderRadius: 8,
                fontSize: 12,
              }}
              formatter={(value: number) => [value, "Invoices"]}
            />
            <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={20}>
              {chartData.map((entry, idx) => (
                <Cell key={idx} fill={entry.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
