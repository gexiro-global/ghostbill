import { motion } from 'framer-motion';
import { Container, FileText, Wallet, Bell } from 'lucide-react';

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

const steps = [
  {
    num: '01',
    title: 'Deploy',
    desc: 'Run the Docker image. Configure wallet RPC. Expose as Tor hidden service.',
    icon: Container,
  },
  {
    num: '02',
    title: 'Create Invoice',
    desc: 'One API call generates a unique subaddress. Set amount, description, expiry.',
    icon: FileText,
  },
  {
    num: '03',
    title: 'Customer Pays',
    desc: 'GhostBill monitors mempool and blockchain. Detects payments in seconds.',
    icon: Wallet,
  },
  {
    num: '04',
    title: 'Receive Webhook',
    desc: 'HMAC-signed event fires to your server. Verify, fulfill, done.',
    icon: Bell,
  },
];

export default function HowItWorks() {
  return (
    <section id="how-it-works" className="py-24 lg:py-32 px-6 lg:px-8 border-t border-gb-border">
      <div className="max-w-6xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
          className="mb-16"
        >
          <h2 className="font-heading text-4xl font-bold text-gb-text uppercase tracking-tighter">
            How It Works
          </h2>
          <p className="mt-3 font-mono text-sm text-gb-muted">
            Four steps from deployment to payment.
          </p>
        </motion.div>

        {/* Desktop: horizontal timeline */}
        <motion.div
          variants={container}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true }}
          className="hidden lg:block relative"
        >
          {/* Connecting line */}
          <div className="absolute top-[28px] left-[12.5%] right-[12.5%] h-px bg-gb-border" />

          <div className="grid grid-cols-4 gap-8">
            {steps.map((step) => {
              const Icon = step.icon;
              return (
                <motion.div key={step.num} variants={item} className="text-center relative">
                  {/* Dot on line */}
                  <div className="mx-auto w-2 h-2 rounded-full bg-gb-primary mb-6" />

                  <span className="block font-mono text-4xl font-bold text-gb-primary">
                    {step.num}
                  </span>
                  <Icon size={24} className="mx-auto mt-3 text-gb-muted" />
                  <h3 className="mt-4 font-heading text-lg text-gb-text uppercase tracking-tighter">
                    {step.title}
                  </h3>
                  <p className="mt-2 font-mono text-sm text-gb-muted max-w-[220px] mx-auto leading-relaxed">
                    {step.desc}
                  </p>
                </motion.div>
              );
            })}
          </div>
        </motion.div>

        {/* Mobile: vertical timeline */}
        <motion.div
          variants={container}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true }}
          className="lg:hidden relative"
        >
          {/* Vertical line */}
          <div className="absolute left-[15px] top-0 bottom-0 w-px bg-gb-border" />

          <div className="space-y-12">
            {steps.map((step) => {
              const Icon = step.icon;
              return (
                <motion.div key={step.num} variants={item} className="flex gap-6 relative">
                  {/* Dot */}
                  <div className="flex-shrink-0 w-[30px] flex justify-center pt-1">
                    <div className="w-2 h-2 rounded-full bg-gb-primary" />
                  </div>

                  <div>
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-2xl font-bold text-gb-primary">
                        {step.num}
                      </span>
                      <Icon size={20} className="text-gb-muted" />
                    </div>
                    <h3 className="mt-2 font-heading text-lg text-gb-text uppercase tracking-tighter">
                      {step.title}
                    </h3>
                    <p className="mt-1 font-mono text-sm text-gb-muted leading-relaxed">
                      {step.desc}
                    </p>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </motion.div>
      </div>
    </section>
  );
}
