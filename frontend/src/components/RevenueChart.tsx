"use client";
import { useState, useEffect } from "react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts";
import { TrendingUp } from "lucide-react";
import { api } from "@/lib/api";

interface RevenueDayPoint {
  date: string;
  count: number;
  amount_atomic: number;
  amount_xmr: string;
}

interface RevenueData {
  period: string;
  data: RevenueDayPoint[];
  total_atomic: number;
  total_xmr: string;
  total_payments: number;
}

const PERIODS = [
  { value: "7d", label: "7D" },
  { value: "30d", label: "30D" },
  { value: "90d", label: "90D" },
  { value: "1y", label: "1Y" },
];

function formatXmrShort(xmr: string): string {
  const n = parseFloat(xmr);
  if (n === 0) return "0";
  if (n < 0.001) return n.toFixed(6);
  if (n < 1) return n.toFixed(4);
  return n.toFixed(2);
}

export default function RevenueChart() {
  const [period, setPeriod] = useState("30d");
  const [data, setData] = useState<RevenueData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .get<RevenueData>(`/analytics/revenue?period=${period}`)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed"))
      .finally(() => setLoading(false));
  }, [period]);

  const chartData = (data?.data || []).map((d) => ({
    date: d.date.slice(5),
    xmr: parseFloat(d.amount_xmr),
    count: d.count,
  }));

  return (
    <div className="gb-card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-gb-accent" />
          <h2 className="font-heading text-lg font-semibold text-gb-text-primary">
            Revenue
          </h2>
          {data && (
            <span className="text-sm text-gb-text-secondary ml-2">
              {formatXmrShort(data.total_xmr)} XMR total ({data.total_payments} payments)
            </span>
          )}
        </div>
        <div className="flex gap-1">
          {PERIODS.map((p) => (
            <button
              key={p.value}
              onClick={() => setPeriod(p.value)}
              className={`px-3 py-1 text-xs font-mono rounded-gb transition-colors ${
                period === p.value
                  ? "bg-gb-accent text-white"
                  : "text-gb-text-secondary hover:text-gb-text-primary hover:bg-gb-border/30"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="h-[240px] bg-gb-border/10 rounded animate-pulse" />
      ) : error ? (
        <div className="h-[240px] flex items-center justify-center text-gb-error text-sm">
          {error}
        </div>
      ) : chartData.length === 0 ? (
        <div className="h-[240px] flex items-center justify-center text-gb-text-secondary text-sm">
          No revenue data for this period
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="revenueGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#ff6b2d" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#ff6b2d" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1a1a2e" />
            <XAxis
              dataKey="date"
              tick={{ fill: "#6b6b8a", fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: "#1a1a2e" }}
            />
            <YAxis
              tick={{ fill: "#6b6b8a", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={50}
              tickFormatter={(v: number) => (v < 1 ? v.toFixed(2) : v.toFixed(0))}
            />
            <Tooltip
              contentStyle={{
                background: "#0f0f1a",
                border: "1px solid #1a1a2e",
                borderRadius: 8,
                fontSize: 12,
              }}
              labelStyle={{ color: "#8a8aaa" }}
              formatter={(value: number) => [`${value.toFixed(4)} XMR`, "Revenue"]}
            />
            <Area
              type="monotone"
              dataKey="xmr"
              stroke="#ff6b2d"
              strokeWidth={2}
              fill="url(#revenueGrad)"
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
