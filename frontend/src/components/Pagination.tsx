"use client";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface PaginationProps {
  total: number;
  limit: number;
  offset: number;
  onPageChange: (offset: number) => void;
}

export default function Pagination({ total, limit, offset, onPageChange }: PaginationProps) {
  if (total <= limit) return null;

  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit);
  const hasPrev = offset > 0;
  const hasNext = offset + limit < total;

  return (
    <div className="flex items-center justify-between pt-4">
      <p className="text-sm text-gb-text-secondary">
        Showing {offset + 1}–{Math.min(offset + limit, total)} of {total}
      </p>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onPageChange(Math.max(0, offset - limit))}
          disabled={!hasPrev}
          className="p-2 rounded-gb border border-gb-border text-gb-text-secondary hover:text-gb-text-primary hover:border-gb-accent disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        <span className="text-sm text-gb-text-secondary px-2">
          {currentPage} / {totalPages}
        </span>
        <button
          onClick={() => onPageChange(offset + limit)}
          disabled={!hasNext}
          className="p-2 rounded-gb border border-gb-border text-gb-text-secondary hover:text-gb-text-primary hover:border-gb-accent disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
