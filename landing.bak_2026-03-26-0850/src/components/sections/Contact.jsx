import { useTranslation } from 'react-i18next';
import { Mail, Github, MessageCircle } from 'lucide-react';
import { motion } from 'framer-motion';

const channels = [
  {
    key: 'email',
    icon: Mail,
    href: 'mailto:contact@ghostbill.org',
    color: 'gb-primary',
  },
  {
    key: 'github',
    icon: Github,
    href: 'https://github.com/nicknull/ghostbill/issues',
    color: 'gb-muted',
  },
  {
    key: 'matrix',
    icon: MessageCircle,
    href: 'https://matrix.to/#/#ghostbill:matrix.org',
    color: 'gb-teal',
  },
];

export default function Contact() {
  const { t } = useTranslation();

  return (
    <section id="contact" className="py-24 bg-gb-bg border-t border-gb-border">
      <div className="max-w-4xl mx-auto px-6 lg:px-8">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4 }}
          className="text-center mb-16"
        >
          <h2 className="font-heading text-3xl md:text-4xl font-bold text-gb-text">
            {t('contact.title')}
          </h2>
          <p className="mt-4 font-mono text-sm text-gb-muted max-w-xl mx-auto">
            {t('contact.subtitle')}
          </p>
        </motion.div>

        {/* Channel cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {channels.map((channel, i) => (
            <motion.a
              key={channel.key}
              href={channel.href}
              target={channel.key === 'email' ? '_self' : '_blank'}
              rel="noopener noreferrer"
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.1 }}
              className="group block bg-gb-surface border border-gb-border p-8 text-center hover:border-gb-primary/40 transition-colors duration-200"
            >
              <channel.icon
                className={`w-8 h-8 text-${channel.color} mx-auto mb-4 group-hover:text-gb-primary transition-colors duration-200`}
              />
              <h3 className="font-heading text-lg font-bold text-gb-text mb-2">
                {t(`contact.${channel.key}Title`)}
              </h3>
              <p className="font-mono text-xs text-gb-muted mb-4 leading-relaxed">
                {t(`contact.${channel.key}Desc`)}
              </p>
              <span className="font-mono text-xs text-gb-primary group-hover:text-gb-primaryHover transition-colors duration-200">
                {t(`contact.${channel.key}Label`)}
              </span>
            </motion.a>
          ))}
        </div>

        {/* Response time note */}
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, delay: 0.4 }}
          className="text-center mt-10 font-mono text-[11px] text-gb-dim"
        >
          {t('contact.response')}
        </motion.p>
      </div>
    </section>
  );
}
