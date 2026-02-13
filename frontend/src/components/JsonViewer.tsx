"use client";

import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import CopyButton from "@/components/CopyButton";

interface JsonViewerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  data: Record<string, unknown> | string | null;
}

export default function JsonViewer({ open, onClose, title, data }: JsonViewerProps) {
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

  const jsonString =
    typeof data === "string" ? data : JSON.stringify(data, null, 2);

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
    >
      <div className="bg-gb-card border border-gb-border rounded-gb shadow-2xl w-full max-w-2xl mx-4 max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gb-border">
          <h3 className="text-lg font-heading font-semibold text-gb-text-primary">
            {title}
          </h3>
          <div className="flex items-center gap-3">
            <CopyButton text={jsonString || ""} label="Copy" />
            <button
              onClick={onClose}
              className="text-gb-text-secondary hover:text-gb-text-primary transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* JSON Content */}
        <div className="overflow-auto flex-1 p-6">
          <pre className="font-mono text-sm text-gb-text-primary whitespace-pre-wrap break-words leading-relaxed">
            {jsonString || "No data"}
          </pre>
        </div>
      </div>
    </div>
  );
}
