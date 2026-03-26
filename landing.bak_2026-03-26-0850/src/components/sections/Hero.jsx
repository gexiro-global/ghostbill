import { useState } from 'react';
import { motion } from 'framer-motion';
import { Ghost, Terminal, Copy, Check } from 'lucide-react';

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

const curlCommand = `curl -X POST https://api.ghostbill.org/v1/invoices \\
  -H "Authorization: Bearer gb_live_..." \\
  -H "Content-Type: application/json" \\
  -d '{"amount_xmr": "0.5", "description": "VPN 1 month"}'`;

export default function Hero() {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(curlCommand);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* fallback for Tor Browser */
      const textarea = document.createElement('textarea');
      textarea.value = curlCommand;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <section className="relative min-h-[80vh] pt-32 pb-24 overflow-hidden">
      {/* Ghost watermark */}
      <motion.div
        animate={{ y: [0, -6, 0] }}
        transition={{ duration: 8, repeat: Infinity, ease: 'easeInOut' }}
        className="absolute -top-20 -left-20 pointer-events-none opacity-[0.06]"
      >
        <Ghost size={600} className="text-gb-primary" />
      </motion.div>

      {/* Orange radial glow */}
      <div className="absolute top-1/4 left-1/4 w-[600px] h-[600px] bg-gb-primary/5 rounded-full blur-[120px] pointer-events-none" />

      <div className="relative z-10 max-w-6xl mx-auto px-6 lg:px-8">
        <motion.div
          variants={container}
          initial="hidden"
          animate="show"
          className="grid lg:grid-cols-2 gap-12 items-center"
        >
          {/* Left column — text */}
          <div>
            <motion.div variants={item} className="flex items-center gap-3 mb-8">
              <Ghost size={28} className="text-gb-primary" />
              <span className="font-mono text-xs text-gb-primary tracking-widest uppercase">
                PROTOCOL v1.0-beta
              </span>
            </motion.div>

            <motion.h1
              variants={item}
              className="font-heading text-5xl md:text-7xl font-bold uppercase tracking-tighter leading-[0.9]"
            >
              <span className="block text-gb-text">Accept Monero.</span>
              <span className="block text-gb-text mt-2">Without Trusting Anyone.</span>
            </motion.h1>

            <motion.p variants={item} className="mt-6 text-lg text-gb-muted max-w-lg font-body">
              Non-custodial, Tor-native payment processor for Monero merchants. No
              accounts. No custody. No surveillance.
            </motion.p>

            <motion.p variants={item} className="mt-2 font-mono text-sm text-gb-teal">
              {'// No logs. No fees. No trace.'}
            </motion.p>

            <motion.div variants={item} className="mt-10 flex flex-wrap gap-4">
              <a
                href="#deploy"
                className="px-8 py-4 bg-gb-primary hover:bg-gb-primaryHover text-gb-bg font-heading font-bold rounded-lg transition-colors duration-200"
              >
                DEPLOY NOW
              </a>
              <a
                href="https://github.com/nicknull/ghostbill"
                target="_blank"
                rel="noopener noreferrer"
                className="px-8 py-4 border border-gb-border hover:border-gb-muted text-gb-text font-heading rounded-lg transition-colors duration-200"
              >
                DOCUMENTATION
              </a>
            </motion.div>

            <motion.p variants={item} className="mt-6 font-mono text-[11px] text-gb-dim tracking-widest">
              AGPL-3.0 · Self-Hosted · 0% Fees
            </motion.p>
          </div>

          {/* Right column — terminal */}
          <motion.div
            variants={item}
            className="border border-gb-border bg-gb-surface"
          >
            {/* Terminal header */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-gb-border bg-black/50">
              <div className="flex items-center gap-2">
                <Terminal size={14} className="text-gb-dim" />
                <span className="font-mono text-[10px] text-gb-dim tracking-widest uppercase">
                  Interactive Shell
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

              {/* Command */}
              <div className="pr-10">
                <span className="text-gb-primary">$ </span>
                <span className="text-gb-text">curl -X POST </span>
                <span className="text-gb-teal">https://api.ghostbill.org/v1/invoices</span>
                <span className="text-gb-dim"> \</span>
                <br />
                <span className="text-gb-text">{'  '}-H </span>
                <span className="text-gb-teal">"Authorization: Bearer gb_live_..."</span>
                <span className="text-gb-dim"> \</span>
                <br />
                <span className="text-gb-text">{'  '}-H </span>
                <span className="text-gb-teal">"Content-Type: application/json"</span>
                <span className="text-gb-dim"> \</span>
                <br />
                <span className="text-gb-text">{'  '}-d </span>
                <span className="text-gb-teal">
                  {"'{\"amount_xmr\": \"0.5\", \"description\": \"VPN 1 month\"}'"}
                </span>
              </div>

              {/* Cursor */}
              <motion.span
                animate={{ opacity: [0, 1, 0] }}
                transition={{ duration: 1.2, repeat: Infinity, ease: 'easeInOut' }}
                className="inline-block w-[2px] h-4 bg-gb-primary ml-1 mt-4 align-middle"
              />
            </div>

            {/* Response preview */}
            <div className="px-6 pb-6 font-mono text-xs text-gb-dim">
              <span className="text-gb-muted"># → 201 Created</span>
              <br />
              <span>
                {'{ "id": "inv_...", "address": "86jXqk...", "status": "pending" }'}
              </span>
            </div>
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}
