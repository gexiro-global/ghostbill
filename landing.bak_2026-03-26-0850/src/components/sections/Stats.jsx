import { motion } from 'framer-motion';

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.1, delayChildren: 0.2 },
  },
};

const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: 'easeOut' } },
};

const stats = [
  { value: '32', label: 'API Endpoints' },
  { value: '13', label: 'Webhook Events' },
  { value: '7', label: 'Invoice States' },
  { value: '0%', label: 'Transaction Fees' },
];

export default function Stats() {
  return (
    <section className="py-24 border-t border-gb-border bg-gb-surface">
      <div className="max-w-6xl mx-auto px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
          className="mb-12"
        >
          <h2 className="font-heading text-4xl font-bold text-gb-text uppercase tracking-tighter">
            Protocol Snapshot
          </h2>
          <p className="mt-3 font-mono text-sm text-gb-muted">
            Lightweight. Predictable. Auditable.
          </p>
        </motion.div>

        <motion.div
          variants={container}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true }}
          className="grid grid-cols-2 lg:grid-cols-4"
        >
          {stats.map((stat, i) => (
            <motion.div
              key={stat.label}
              variants={item}
              className={`text-center py-8 ${
                i < stats.length - 1 ? 'lg:border-r lg:border-gb-border' : ''
              } ${i < 2 ? 'border-b lg:border-b-0 border-gb-border' : ''} ${
                i % 2 === 0 && i < 2 ? 'border-r lg:border-r border-gb-border' : ''
              }`}
            >
              <span className="block font-mono text-5xl md:text-6xl font-bold text-gb-primary">
                {stat.value}
              </span>
              <span className="block mt-2 font-mono text-sm text-gb-muted uppercase tracking-wider">
                {stat.label}
              </span>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
