import { useState, useEffect, useRef } from 'react';
import { Globe } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';

const languages = [
  { code: 'en', label: 'EN' },
];

export default function LanguageSwitcher() {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-gb-muted hover:text-gb-text transition-colors duration-200 cursor-pointer"
        aria-label="Select language"
      >
        <Globe size={16} />
        <span className="font-mono text-xs tracking-wider">EN</span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 mt-2 bg-gb-elevated border border-gb-border rounded-lg overflow-hidden min-w-[80px]"
          >
            {languages.map((lang) => (
              <button
                key={lang.code}
                onClick={() => setOpen(false)}
                className="w-full px-4 py-2 text-left font-mono text-xs tracking-wider text-gb-primary hover:bg-gb-surface transition-colors cursor-pointer"
              >
                {lang.label}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
