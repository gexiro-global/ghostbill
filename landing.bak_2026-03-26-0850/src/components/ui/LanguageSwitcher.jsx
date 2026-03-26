import { useState, useEffect, useRef } from 'react';
import { Globe } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';

const languages = [
  { code: 'en', label: 'EN' },
  { code: 'de', label: 'DE' },
  { code: 'pl', label: 'PL' },
];

export default function LanguageSwitcher() {
  const { i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  const currentLang = languages.find((l) => l.code === i18n.language) || languages[0];

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleChange = (code) => {
    i18n.changeLanguage(code);
    setOpen(false);
    const url = new URL(window.location);
    if (code === 'en') {
      url.searchParams.delete('lng');
    } else {
      url.searchParams.set('lng', code);
    }
    window.history.replaceState({}, '', url);
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-gb-muted hover:text-gb-text transition-colors duration-200 cursor-pointer"
        aria-label="Select language"
      >
        <Globe size={16} />
        <span className="font-mono text-xs tracking-wider">{currentLang.label}</span>
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
                onClick={() => handleChange(lang.code)}
                className={`w-full px-4 py-2 text-left font-mono text-xs tracking-wider transition-colors cursor-pointer ${
                  lang.code === i18n.language
                    ? 'text-gb-primary bg-gb-surface'
                    : 'text-gb-muted hover:text-gb-text hover:bg-gb-surface'
                }`}
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
