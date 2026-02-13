"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FileText,
  Wallet,
  Code2,
  Settings,
  Ghost,
  LogOut,
} from "lucide-react";
import { getApiKey, isLiveKey, removeApiKey } from "@/lib/api";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/dashboard/invoices", label: "Invoices", icon: FileText },
  { href: "/dashboard/payments", label: "Payments", icon: Wallet },
  { href: "/dashboard/developers", label: "Developers", icon: Code2 },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();
  const apiKey = getApiKey();
  const isLive = apiKey ? isLiveKey(apiKey) : false;

  const handleLogout = () => {
    removeApiKey();
    window.location.href = "/login";
  };

  return (
    <aside className="w-64 h-screen bg-gb-sidebar border-r border-gb-border flex flex-col fixed left-0 top-0">
      {/* Logo */}
      <div className="p-6 border-b border-gb-border">
        <Link href="/dashboard" className="flex items-center gap-3">
          <Ghost className="w-8 h-8 text-gb-accent" />
          <span className="font-heading text-xl font-bold text-gb-text-primary">
            GhostBill
          </span>
        </Link>
      </div>

      {/* Environment badge */}
      <div className="px-6 py-3">
        <span
          className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-medium ${
            isLive
              ? "bg-gb-success/15 text-gb-success border border-gb-success/30"
              : "bg-gb-warning/15 text-gb-warning border border-gb-warning/30"
          }`}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              isLive ? "bg-gb-success" : "bg-gb-warning"
            }`}
          />
          {isLive ? "LIVE" : "TEST"}
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map((item) => {
          const isActive =
            item.href === "/dashboard"
              ? pathname === "/dashboard"
              : pathname.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-gb text-sm font-medium transition-colors duration-200 ${
                isActive
                  ? "bg-gb-accent/10 text-gb-accent border-l-2 border-gb-accent"
                  : "text-gb-text-secondary hover:text-gb-text-primary hover:bg-gb-card"
              }`}
            >
              <item.icon className="w-5 h-5 flex-shrink-0" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Logout */}
      <div className="p-3 border-t border-gb-border">
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-3 py-2.5 rounded-gb text-sm font-medium text-gb-text-secondary hover:text-gb-error hover:bg-gb-error/10 transition-colors duration-200 w-full"
        >
          <LogOut className="w-5 h-5 flex-shrink-0" />
          Disconnect
        </button>
      </div>
    </aside>
  );
}
