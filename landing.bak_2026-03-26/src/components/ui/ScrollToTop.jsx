import { AnimatePresence, motion } from 'framer-motion';
import { ArrowUp } from 'lucide-react';
import useScrollToTop from '../../hooks/useScrollToTop';

export default function ScrollToTop() {
  const { showButton, scrollToTop } = useScrollToTop(400);

  return (
    <AnimatePresence>
      {showButton && (
        <motion.button
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.8 }}
          transition={{ duration: 0.2 }}
          onClick={scrollToTop}
          className="fixed bottom-8 right-8 z-50 p-3 bg-gb-elevated border border-gb-border rounded-lg text-gb-muted hover:text-gb-primary hover:border-gb-primary transition-colors duration-200 cursor-pointer"
          aria-label="Scroll to top"
        >
          <ArrowUp size={20} />
        </motion.button>
      )}
    </AnimatePresence>
  );
}
