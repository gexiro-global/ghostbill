"use client";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface CursorPaginationProps {
  hasMore: boolean;
  hasPrev: boolean;
  onNext: () => void;
  onPrev: () => void;
  loading?: boolean;
}

export default function Pagination({
  hasMore,
  hasPrev,
  onNext,
  onPrev,
  loading,
}: CursorPaginationProps) {
  if (!hasMore && !hasPrev) return null;

  return (
    <div className="flex items-center justify-end gap-2 pt-4">
      <button
        onClick={onPrev}
        disabled={!hasPrev || loading}
        className="p-2 rounded-gb border border-gb-border text-gb-text-secondary hover:text-gb-text-primary hover:border-gb-accent disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        <ChevronLeft className="w-4 h-4" />
      </button>
      <button
        onClick={onNext}
        disabled={!hasMore || loading}
        className="p-2 rounded-gb border border-gb-border text-gb-text-secondary hover:text-gb-text-primary hover:border-gb-accent disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        <ChevronRight className="w-4 h-4" />
      </button>
    </div>
  );
}
