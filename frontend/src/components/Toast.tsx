"use client";

import { createContext, useContext, useState, useCallback, useRef, useEffect } from "react";
import { CheckCircle, XCircle, Info, X } from "lucide-react";

type ToastType = "success" | "error" | "info";

interface Toast {
  id: string;
  type: ToastType;
  message: string;
}

interface ToastContextValue {
  toast: (type: ToastType, message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counterRef = useRef(0);

  const toast = useCallback((type: ToastType, message: string) => {
    const id = `toast-${++counterRef.current}`;
    setToasts((prev) => [...prev, { id, type, message }]);
  }, []);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-3 pointer-events-none">
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({
  toast,
  onDismiss,
}: {
  toast: Toast;
  onDismiss: (id: string) => void;
}) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), 4000);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  const config = {
    success: {
      icon: CheckCircle,
      bg: "bg-gb-success/10 border-gb-success/30",
      text: "text-gb-success",
    },
    error: {
      icon: XCircle,
      bg: "bg-gb-error/10 border-gb-error/30",
      text: "text-gb-error",
    },
    info: {
      icon: Info,
      bg: "bg-gb-info/10 border-gb-info/30",
      text: "text-gb-info",
    },
  }[toast.type];

  const Icon = config.icon;

  return (
    <div
      className={`pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-gb border ${config.bg} shadow-lg min-w-[300px] max-w-[420px] animate-slide-in`}
    >
      <Icon className={`w-5 h-5 flex-shrink-0 ${config.text}`} />
      <span className="text-sm text-gb-text-primary flex-1">{toast.message}</span>
      <button
        onClick={() => onDismiss(toast.id)}
        className="text-gb-text-secondary hover:text-gb-text-primary transition-colors flex-shrink-0"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
