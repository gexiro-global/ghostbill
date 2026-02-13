const PICONERO = BigInt("1000000000000");

/**
 * Format atomic amount (piconero) to XMR string
 * Example: "1500000000000" → "1.500000000000"
 */
export function formatXMR(atomicStr: string, decimals: number = 4): string {
  try {
    const atomic = BigInt(atomicStr);
    const whole = atomic / PICONERO;
    const fraction = atomic % PICONERO;
    const fractionStr = fraction.toString().padStart(12, "0").slice(0, decimals);
    return `${whole}.${fractionStr}`;
  } catch {
    return "0.0000";
  }
}

/**
 * Format fiat amount with currency symbol
 * Example: "49.99", "USD" → "$49.99"
 */
export function formatFiat(amount: string | null, currency: string | null): string {
  if (!amount || !currency) return "—";

  const symbols: Record<string, string> = {
    USD: "$",
    EUR: "€",
    GBP: "£",
    PLN: "zł",
    BTC: "₿",
  };

  const symbol = symbols[currency.toUpperCase()] || currency;
  const num = parseFloat(amount);

  if (isNaN(num)) return "—";

  return `${symbol}${num.toFixed(2)}`;
}

/**
 * Truncate hash/address for display
 * Example: "abc123...def456" (6 + 6 default)
 */
export function truncateHash(hash: string, start: number = 6, end: number = 6): string {
  if (!hash) return "—";
  if (hash.length <= start + end + 3) return hash;
  return `${hash.slice(0, start)}...${hash.slice(-end)}`;
}

/**
 * Relative time from ISO string
 * Example: "2 min ago", "3h ago", "5d ago"
 */
export function timeAgo(isoString: string): string {
  try {
    const now = Date.now();
    const then = new Date(isoString).getTime();
    const diff = now - then;

    if (diff < 0) return "just now";

    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (seconds < 60) return "just now";
    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    if (days < 30) return `${days}d ago`;

    return new Date(isoString).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
  } catch {
    return "—";
  }
}

/**
 * Format ISO date to readable string
 * Example: "Feb 12, 2026, 22:30"
 */
export function formatDate(isoString: string): string {
  try {
    return new Date(isoString).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return "—";
  }
}

/**
 * Copy text to clipboard
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
