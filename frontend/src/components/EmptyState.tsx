import { type LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export default function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="text-center py-16">
      <Icon className="w-12 h-12 mx-auto mb-4 text-gb-text-secondary opacity-30" />
      <p className="text-gb-text-primary font-medium">{title}</p>
      {description && (
        <p className="text-sm text-gb-text-secondary mt-1">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
