import { Ghost } from 'lucide-react';

export default function Logo({ size = 'sm' }) {
  const handleClick = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  if (size === 'lg') {
    return (
      <button onClick={handleClick} className="flex items-center gap-3 cursor-pointer">
        <Ghost size={28} className="text-gb-text" />
        <span className="font-heading text-xl font-bold tracking-tight">
          <span className="text-gb-text">Ghost</span>
          <span className="text-gb-primary">Bill</span>
        </span>
      </button>
    );
  }

  return (
    <button onClick={handleClick} className="flex items-center gap-2 cursor-pointer">
      <Ghost size={22} className="text-gb-text" />
      <span className="font-heading text-lg font-bold tracking-tight">
        <span className="text-gb-text">Ghost</span>
        <span className="text-gb-primary">Bill</span>
      </span>
    </button>
  );
}
