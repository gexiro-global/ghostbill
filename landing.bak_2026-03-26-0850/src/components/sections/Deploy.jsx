import { useState } from 'react';
import { motion } from 'framer-motion';
import { Terminal, Copy, Check } from 'lucide-react';

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

const steps = [
  {
    num: '01',
    title: 'Pull the Image',
    desc: 'Run the official Docker Compose stack.',
  },
  {
    num: '02',
    title: 'Configure Environment',
    desc: 'Set RPC endpoint and wallet connection in .env file.',
  },
  {
    num: '03',
    title: 'Launch the Service',
    desc: 'Expose as Tor hidden service (recommended) or clearnet.',
  },
  {
    num: '04',
    title: 'Create First Invoice',
    desc: 'One API call. Start accepting Monero immediately.',
  },
];

const terminalText = `$ docker compose up -d

✓ Container ghostbill-postgres  Started
✓ Container ghostbill-redis     Started
✓ Container ghostbill-walletrpc Started
✓ Container ghostbill-backend   Started
✓ Container ghostbill-frontend  Started

$ curl http://localhost:8013/health

{"status":"healthy","app":"GhostBill"}`;

export default function Deploy() {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText('docker compose up -d');
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = 'docker compose up -d';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <section id="deploy" className="py-24 lg:py-32 px-6 lg:px-8 border-t border-gb-border bg-gb-surface">
      <div className="max-w-6xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
          className="mb-16"
        >
          <h2 className="font-heading text-4xl font-bold text-gb-text uppercase tracking-tighter">
            Deploy in 15 Minutes
          </h2>
          <p className="mt-3 font-mono text-sm text-gb-muted">
            Self-hosted. No accounts. No vendor lock-in.
          </p>
        </motion.div>

        <motion.div
          variants={container}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true }}
          className="grid lg:grid-cols-2 gap-12 items-start"
        >
          {/* Left — steps */}
          <div className="space-y-8">
            {steps.map((step) => (
              <motion.div
                key={step.num}
                variants={item}
                className="group flex gap-4 items-start"
              >
                <span className="font-mono text-lg font-bold text-gb-dim w-8 flex-shrink-0 border-l-2 border-transparent group-hover:border-gb-primary group-hover:text-gb-primary pl-3 transition-all duration-300">
                  {step.num}
                </span>
                <div>
                  <h3 className="font-heading text-lg text-gb-text uppercase tracking-tighter">
                    {step.title}
                  </h3>
                  <p className="mt-1 font-mono text-sm text-gb-muted">
                    {step.desc}
                  </p>
                </div>
              </motion.div>
            ))}
          </div>

          {/* Right — terminal */}
          <motion.div variants={item} className="border border-gb-border bg-gb-bg">
            {/* Terminal header */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-gb-border bg-black/50">
              <div className="flex items-center gap-2">
                <Terminal size={14} className="text-gb-dim" />
                <span className="font-mono text-[10px] text-gb-dim tracking-widest uppercase">
                  ghostbill-deploy.sh
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-gb-dim text-xs">··</span>
                <span className="text-gb-primary text-xs">●</span>
              </div>
            </div>

            {/* Terminal body */}
            <div className="relative p-6 font-mono text-sm leading-relaxed">
              <button
                onClick={handleCopy}
                className={`absolute top-3 right-3 p-1.5 border rounded transition-colors duration-200 cursor-pointer ${
                  copied
                    ? 'border-gb-teal text-gb-teal'
                    : 'border-gb-border text-gb-dim hover:text-gb-muted hover:border-gb-muted'
                }`}
                aria-label="Copy command"
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
              </button>

              {/* Commands */}
              <div className="pr-10">
                <span className="text-gb-primary">$ </span>
                <span className="text-gb-text">docker compose up -d</span>
              </div>

              <div className="mt-4 space-y-1">
                {[
                  'ghostbill-postgres',
                  'ghostbill-redis',
                  'ghostbill-walletrpc',
                  'ghostbill-backend',
                  'ghostbill-frontend',
                ].map((name) => (
                  <div key={name}>
                    <span className="text-gb-teal">✓</span>
                    <span className="text-gb-text"> Container {name}</span>
                    <span className="text-gb-teal">  Started</span>
                  </div>
                ))}
              </div>

              <div className="mt-4">
                <span className="text-gb-primary">$ </span>
                <span className="text-gb-text">curl http://localhost:8013/health</span>
              </div>

              <div className="mt-2 text-gb-dim">
                {'{"status":"healthy","app":"GhostBill"}'}
              </div>
            </div>

            {/* Status line */}
            <div className="px-6 pb-4">
              <span className="font-mono text-[10px] text-gb-dim tracking-widest uppercase">
                <span className="text-gb-teal">●</span> Running
              </span>
            </div>
          </motion.div>
        </motion.div>

        {/* CTA */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, delay: 0.3 }}
          className="mt-12 text-center"
        >
          <a
            href="https://github.com/nicknull/ghostbill"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block px-8 py-4 bg-gb-primary hover:bg-gb-primaryHover text-gb-bg font-heading font-bold rounded-lg transition-colors duration-200"
          >
            DEPLOY NOW
          </a>
        </motion.div>
      </div>
    </section>
  );
}
