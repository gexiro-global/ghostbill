"use client";

import { useEffect, useRef } from "react";
import { AlertTriangle, X } from "lucide-react";

interface ConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  loading?: boolean;
}

export default function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
  loading = false,
}: ConfirmDialogProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };

    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
    >
      <div className="bg-gb-card border border-gb-border rounded-gb shadow-2xl w-full max-w-md mx-4 p-6">
        {/* Header */}
        <div className="flex items-start gap-3 mb-4">
          {destructive && (
            <div className="w-10 h-10 rounded-full bg-gb-error/15 flex items-center justify-center flex-shrink-0">
              <AlertTriangle className="w-5 h-5 text-gb-error" />
            </div>
          )}
          <div className="flex-1">
            <h3 className="text-lg font-heading font-semibold text-gb-text-primary">
              {title}
            </h3>
            <p className="text-sm text-gb-text-secondary mt-1">{message}</p>
          </div>
          <button
            onClick={onClose}
            className="text-gb-text-secondary hover:text-gb-text-primary transition-colors flex-shrink-0"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-3 mt-6">
          <button
            onClick={onClose}
            disabled={loading}
            className="gb-btn-secondary px-4 py-2 text-sm"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className={`px-4 py-2 text-sm font-medium rounded-gb transition-colors ${
              destructive
                ? "bg-gb-error hover:bg-gb-error/80 text-white"
                : "gb-btn-primary"
            } ${loading ? "opacity-50 cursor-not-allowed" : ""}`}
          >
            {loading ? "Processing..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
