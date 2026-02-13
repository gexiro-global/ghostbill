import type { InvoiceStatus, PaymentStatus } from "@/lib/types";

type StatusType = InvoiceStatus | PaymentStatus;

interface StatusBadgeProps {
  status: StatusType;
  type?: "invoice" | "payment";
  size?: "sm" | "md";
}

const statusConfig: Record<StatusType, { label: string; color: string }> = {
  // Invoice statuses
  pending: {
    label: "Pending",
    color: "bg-gb-warning/15 text-gb-warning border-gb-warning/30",
  },
  paid: {
    label: "Paid",
    color: "bg-gb-success/15 text-gb-success border-gb-success/30",
  },
  expired: {
    label: "Expired",
    color: "bg-gb-text-secondary/15 text-gb-text-secondary border-gb-text-secondary/30",
  },
  partially_paid: {
    label: "Partial",
    color: "bg-gb-warning/15 text-gb-warning border-gb-warning/30",
  },
  overpaid: {
    label: "Overpaid",
    color: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  },
  late_paid: {
    label: "Late Paid",
    color: "bg-gb-accent/15 text-gb-accent border-gb-accent/30",
  },
  cancelled: {
    label: "Cancelled",
    color: "bg-gb-error/15 text-gb-error border-gb-error/30",
  },
  // Payment statuses
  detected: {
    label: "Detected",
    color: "bg-gb-warning/15 text-gb-warning border-gb-warning/30",
  },
  confirmed: {
    label: "Confirmed",
    color: "bg-gb-success/15 text-gb-success border-gb-success/30",
  },
  orphaned: {
    label: "Orphaned",
    color: "bg-gb-error/15 text-gb-error border-gb-error/30",
  },
};

export function StatusBadge({ status, size = "sm" }: StatusBadgeProps) {
  const config = statusConfig[status];

  if (!config) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono border bg-gb-card text-gb-text-secondary border-gb-border">
        {status}
      </span>
    );
  }

  const sizeClasses = size === "sm" ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm";

  return (
    <span
      className={`inline-flex items-center rounded font-mono font-medium border ${config.color} ${sizeClasses}`}
    >
      {config.label}
    </span>
  );
}

export default StatusBadge;
