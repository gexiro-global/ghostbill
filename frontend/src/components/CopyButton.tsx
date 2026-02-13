"use client";
import { useState } from "react";
import { Copy, Check } from "lucide-react";

interface CopyButtonProps {
  text: string;
  label?: string;
  className?: string;
}

export default function CopyButton({ text, label, className = "" }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <button
      onClick={handleCopy}
      className={`inline-flex items-center gap-1.5 text-sm text-gb-text-secondary hover:text-gb-accent transition-colors ${className}`}
      title={copied ? "Copied!" : `Copy ${label || "to clipboard"}`}
    >
      {label && <span>{label}</span>}
      {copied ? (
        <Check className="w-4 h-4 text-gb-success" />
      ) : (
        <Copy className="w-4 h-4" />
      )}
    </button>
  );
}
