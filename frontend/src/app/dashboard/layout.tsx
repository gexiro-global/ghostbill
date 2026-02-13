"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getApiKey } from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import { ToastProvider } from "@/components/Toast";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const apiKey = getApiKey();
    if (!apiKey) {
      router.push("/login");
    } else {
      setReady(true);
    }
  }, [router]);

  if (!ready) {
    return (
      <div className="min-h-screen bg-gb-bg flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-gb-accent border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <ToastProvider>
      <div className="min-h-screen bg-gb-bg">
        <Sidebar />
        <main className="ml-64 min-h-screen">
          <div className="p-8">{children}</div>
        </main>
      </div>
    </ToastProvider>
  );
}
