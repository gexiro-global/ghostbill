import { motion } from 'framer-motion';
import { Shield, Globe, Bell, GitBranch, RefreshCw, Server } from 'lucide-react';

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.08, delayChildren: 0.2 },
  },
};

const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: 'easeOut' } },
};

const features = [
  {
    num: '01',
    tag: '// SECURITY',
    title: 'Non-Custodial Core',
    icon: Shield,
    desc: 'GhostBill never holds private keys or funds. Payments go directly from customer to merchant wallet. No intermediaries. No custody risk.',
  },
  {
    num: '02',
    tag: '// NETWORK',
    title: 'Tor-Native Infrastructure',
    icon: Globe,
    desc: 'Runs as a Tor hidden service by default. All outgoing connections routed through Tor. Privacy is the baseline, not an option.',
  },
  {
    num: '03',
    tag: '// WEBHOOKS',
    title: 'Event-Driven API',
    icon: Bell,
    desc: '13 webhook events covering the full invoice and subscription lifecycle. HMAC-SHA256 signed. 7 automatic retries. Build reactive systems without polling.',
  },
  {
    num: '04',
    tag: '// INVOICES',
    title: 'Deterministic State Machine',
    icon: GitBranch,
    desc: '7 invoice states with explicit transitions. Partial payments, overpayments, late payments — all handled automatically. No hidden failures.',
  },
  {
    num: '05',
    tag: '// SUBSCRIPTIONS',
    title: 'Recurring Billing Engine',
    icon: RefreshCw,
    desc: 'Customer management, automated renewal with configurable grace periods, 5-status subscription lifecycle. Deterministic billing anchors prevent drift.',
  },
  {
    num: '06',
    tag: '// INFRA',
    title: 'Deploy Anywhere',
    icon: Server,
    desc: 'Docker Compose deployment. 5 containers, 15 minutes setup. Runs on VPS, bare metal, or local node. No SaaS dependency. Ever.',
  },
];

export default function Features() {
  return (
    <section id="features" className="py-24 lg:py-32 px-6 lg:px-8 border-t border-gb-border">
      <div className="max-w-6xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
          className="mb-16"
        >
          <h2 className="font-heading text-4xl font-bold text-gb-text uppercase tracking-tighter">
            Infrastructure You Control
          </h2>
          <p className="mt-3 font-mono text-sm text-gb-muted">
            Self-hosted, auditable, deterministic.
          </p>
        </motion.div>

        <motion.div
          variants={container}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true }}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-px bg-gb-border border border-gb-border"
        >
          {features.map((f) => {
            const Icon = f.icon;
            return (
              <motion.div
                key={f.num}
                variants={item}
                className="bg-gb-bg p-8 relative group transition-all duration-300 hover:bg-gb-surface"
              >
                {/* Number */}
                <span className="absolute top-4 right-4 font-mono text-[10px] text-gb-border group-hover:text-gb-primary transition-colors duration-300">
                  [{f.num}]
                </span>

                {/* Icon */}
                <Icon
                  size={28}
                  strokeWidth={1.5}
                  className="text-gb-muted group-hover:text-gb-primary transition-colors duration-300"
                />

                {/* Tag */}
                <p className="mt-4 font-mono text-[10px] text-gb-primary tracking-[0.2em]">
                  {f.tag}
                </p>

                {/* Title */}
                <h3 className="mt-2 font-heading text-xl text-gb-text uppercase tracking-tighter">
                  {f.title}
                </h3>

                {/* Description */}
                <p className="mt-3 font-mono text-sm text-gb-muted leading-relaxed">
                  {f.desc}
                </p>

                {/* Bottom accent line */}
                <span className="absolute bottom-0 left-0 h-[2px] w-0 bg-gb-primary transition-all duration-500 group-hover:w-full" />
              </motion.div>
            );
          })}
        </motion.div>

        {/* Subtle link */}
        <div className="mt-12 text-center">
          <a
            href="https://github.com/nicknull/ghostbill"
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono text-[11px] text-gb-muted border-b border-gb-border hover:text-gb-primary hover:border-gb-primary transition-colors duration-200"
          >
            EXPLORE API DOCUMENTATION →
          </a>
        </div>
      </div>
    </section>
  );
}
