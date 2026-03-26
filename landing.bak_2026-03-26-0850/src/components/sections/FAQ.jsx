import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown } from 'lucide-react';

const faqs = [
  {
    q: 'Does GhostBill ever hold private keys?',
    a: 'No. GhostBill uses your secret view key to detect payments. Private spend keys never touch the server. Even full root compromise cannot move funds.',
  },
  {
    q: 'How are payments verified?',
    a: 'Invoices are monitored through wallet-RPC connected to your Monero node. Payment state transitions occur after required block confirmations. No off-chain heuristics.',
  },
  {
    q: 'What happens if the server restarts?',
    a: 'Invoice state is persisted in PostgreSQL. On restart, GhostBill re-syncs pending invoices against the node. No payments are lost.',
  },
  {
    q: 'Is Tor required?',
    a: 'Tor is recommended and enabled by default. Clearnet access can be configured but internally all outgoing connections (webhooks, price feeds) route through Tor.',
  },
  {
    q: 'Does GhostBill charge fees?',
    a: 'No. Zero protocol fees, zero platform fees. You control the infrastructure. Payments go directly from customer to your wallet.',
  },
  {
    q: 'Can I audit the code?',
    a: 'Yes. GhostBill is licensed under AGPL-3.0. Full source code is available. You can review, modify, and deploy your own version.',
  },
];

export default function FAQ() {
  const [openIndex, setOpenIndex] = useState(null);

  const toggle = (i) => {
    setOpenIndex(openIndex === i ? null : i);
  };

  return (
    <section id="faq" className="py-24 lg:py-32 px-6 lg:px-8 border-t border-gb-border">
      <div className="max-w-3xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
          className="mb-16"
        >
          <h2 className="font-heading text-4xl font-bold text-gb-text uppercase tracking-tighter">
            FAQ
          </h2>
          <p className="mt-3 font-mono text-sm text-gb-muted">
            Technical questions answered.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, delay: 0.2 }}
          className="divide-y divide-gb-border border-t border-b border-gb-border"
        >
          {faqs.map((faq, i) => (
            <div key={i}>
              <button
                onClick={() => toggle(i)}
                className="w-full flex items-center justify-between py-6 text-left cursor-pointer group"
              >
                <span className="font-heading text-lg text-gb-text pr-4 group-hover:text-gb-primary transition-colors duration-200">
                  {faq.q}
                </span>
                <ChevronDown
                  size={20}
                  className={`text-gb-dim flex-shrink-0 transition-transform duration-300 ${
                    openIndex === i ? 'rotate-180 text-gb-primary' : ''
                  }`}
                />
              </button>

              <AnimatePresence>
                {openIndex === i && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.3, ease: 'easeOut' }}
                    className="overflow-hidden"
                  >
                    <p className="pb-6 font-mono text-sm text-gb-muted leading-relaxed">
                      {faq.a}
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
