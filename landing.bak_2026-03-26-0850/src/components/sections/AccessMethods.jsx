import { motion } from 'framer-motion';
import { Globe, ShieldAlert, Zap, Lock } from 'lucide-react';

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.15, delayChildren: 0.2 },
  },
};

const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: 'easeOut' } },
};

export default function AccessMethods() {
  return (
    <section className="py-24 lg:py-32 px-6 lg:px-8 border-t border-gb-border bg-gb-bg">
      <div className="max-w-6xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
          className="mb-16"
        >
          <h2 className="font-heading text-4xl font-bold uppercase tracking-tighter">
            <span className="text-gb-text">Access </span>
            <span className="text-gb-primary">Methods</span>
          </h2>
          <p className="mt-3 font-mono text-sm text-gb-muted">
            Choose your connection layer. Privacy is the default.
          </p>
        </motion.div>

        <motion.div
          variants={container}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true }}
          className="grid md:grid-cols-2 gap-0 border border-gb-border"
        >
          {/* Clearnet card */}
          <motion.div
            variants={item}
            className="p-10 lg:p-12 border-b md:border-b-0 md:border-r border-gb-border hover:bg-white/[0.01] transition-colors duration-300"
          >
            <div className="p-3 bg-gb-primary/10 text-gb-primary inline-block">
              <Globe size={24} />
            </div>

            <h3 className="mt-6 font-heading text-xl text-gb-text uppercase tracking-tighter">
              Clearnet
            </h3>

            <ul className="mt-6 space-y-4">
              {[
                'Standard HTTPS routing for high-speed API calls',
                'Cloudflare DDoS protection for public endpoints',
                'ghostbill.org / api.ghostbill.org',
              ].map((text, i) => (
                <li key={i} className="flex items-start gap-3 font-mono text-sm text-gb-muted">
                  <Zap size={14} className="text-gb-primary mt-0.5 flex-shrink-0" />
                  <span>{text}</span>
                </li>
              ))}
            </ul>

            <div className="mt-8">
              <p className="font-mono text-[10px] text-gb-dim tracking-widest uppercase">
                Endpoint Status: <span className="text-green-500">Active</span>
              </p>
              <div className="mt-3 bg-black p-3 border border-gb-border">
                <code className="font-mono text-xs text-gb-primary">api.ghostbill.org</code>
              </div>
            </div>
          </motion.div>

          {/* Tor card */}
          <motion.div
            variants={item}
            className="p-10 lg:p-12 bg-gb-surface relative overflow-hidden group hover:shadow-[inset_0_0_50px_rgba(0,194,168,0.05)] transition-all duration-500"
          >
            {/* Scan lines overlay */}
            <div
              className="absolute inset-0 opacity-0 group-hover:opacity-[0.08] transition-opacity duration-500 pointer-events-none"
              style={{
                backgroundImage:
                  'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,194,168,0.15) 2px, rgba(0,194,168,0.15) 4px)',
              }}
            />

            <div className="relative z-10">
              <div className="p-3 bg-gb-teal/10 text-gb-teal inline-block shadow-[0_0_15px_rgba(0,194,168,0.2)]">
                <ShieldAlert size={24} />
              </div>

              <h3 className="mt-6 font-heading text-xl text-gb-text uppercase tracking-tighter group-hover:text-gb-teal transition-colors duration-300">
                Tor Network
              </h3>

              <ul className="mt-6 space-y-4">
                {[
                  'End-to-end onion routing. No IP metadata leak.',
                  'Native V3 hidden service for API + Dashboard.',
                  'All outgoing webhooks routed through Tor.',
                ].map((text, i) => (
                  <li key={i} className="flex items-start gap-3 font-mono text-sm text-gb-muted">
                    <Lock size={14} className="text-gb-teal mt-0.5 flex-shrink-0" />
                    <span>{text}</span>
                  </li>
                ))}
              </ul>

              <div className="mt-8">
                <p className="font-mono text-[10px] text-gb-dim tracking-widest uppercase">
                  Onion Status: <span className="text-gb-teal animate-pulse">Encrypted</span>
                </p>
                <div className="mt-3 flex items-center gap-2 bg-black p-3 border border-gb-teal/30 group-hover:border-gb-teal transition-colors duration-300">
                  <code className="font-mono text-xs text-gb-teal truncate">
                    bfmpzvpn53lky...uad.onion
                  </code>
                </div>
              </div>
            </div>
          </motion.div>
        </motion.div>

        {/* Privacy disclosure */}
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, delay: 0.4 }}
          className="mt-8 text-center max-w-3xl mx-auto font-mono text-[10px] text-gb-dim uppercase tracking-widest leading-relaxed"
        >
          GhostBill does not collect IP addresses, cookies, or browser fingerprints on
          either access method. Tor provides maximum privacy — no third party sees your
          traffic. Clearnet routes through Cloudflare, which sees connection metadata.
          Your Monero transactions remain private regardless.
        </motion.p>
      </div>
    </section>
  );
}
