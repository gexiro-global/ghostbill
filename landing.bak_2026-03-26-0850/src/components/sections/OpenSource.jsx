import { motion } from 'framer-motion';
import { Check } from 'lucide-react';

const bullets = [
  'Audit the code — full source available',
  'Modify freely — fork and customize',
  'Deploy anywhere — no vendor lock-in',
  'No telemetry — zero phone-home',
];

export default function OpenSource() {
  return (
    <section className="py-24 lg:py-32 px-6 lg:px-8 border-t border-gb-border bg-gb-bg">
      <div className="max-w-6xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
          className="grid lg:grid-cols-2 gap-12 items-center"
        >
          {/* Left — AGPL badge */}
          <div>
            <h2 className="font-heading text-6xl md:text-7xl font-bold text-gb-primary uppercase">
              AGPL-3.0
            </h2>
            <p className="mt-3 font-mono text-sm text-gb-muted tracking-widest uppercase">
              Open Source License
            </p>
            <p className="mt-2 font-body text-lg text-gb-dim">
              Free as in freedom.
            </p>
          </div>

          {/* Right — bullets */}
          <div className="space-y-5">
            {bullets.map((text, i) => (
              <div key={i} className="flex items-start gap-3">
                <Check size={18} className="text-gb-teal mt-0.5 flex-shrink-0" />
                <span className="font-mono text-sm text-gb-muted leading-relaxed">
                  {text}
                </span>
              </div>
            ))}

            <div className="pt-4">
              <a
                href="https://github.com/nicknull/ghostbill"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block px-8 py-4 border border-gb-border hover:border-gb-muted text-gb-text font-heading rounded-lg transition-colors duration-200"
              >
                VIEW ON GITHUB
              </a>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
