import Logo from '../ui/Logo';

const links = {
  Documentation: [
    { label: 'API Reference', href: 'https://github.com/nicknull/ghostbill' },
    { label: 'Webhooks', href: 'https://github.com/nicknull/ghostbill' },
    { label: 'Deployment', href: 'https://github.com/nicknull/ghostbill' },
    { label: 'Security', href: 'https://github.com/nicknull/ghostbill' },
  ],
  Project: [
    { label: 'GitHub', href: 'https://github.com/nicknull/ghostbill' },
    { label: 'Changelog', href: 'https://github.com/nicknull/ghostbill' },
    { label: 'Roadmap', href: 'https://github.com/nicknull/ghostbill' },
    { label: 'License', href: 'https://github.com/nicknull/ghostbill' },
  ],
  Community: [
    { label: 'Monero Community', href: 'https://www.getmonero.org/community/' },
    { label: 'Report Issue', href: 'https://github.com/nicknull/ghostbill/issues' },
    { label: 'Contributing', href: 'https://github.com/nicknull/ghostbill' },
  ],
};

export default function Footer() {
  return (
    <footer className="border-t border-gb-border bg-gb-surface">
      <div className="max-w-6xl mx-auto px-6 lg:px-8 py-16">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-12">
          {/* Brand column */}
          <div>
            <Logo size="lg" />
            <p className="mt-4 font-mono text-sm text-gb-muted leading-relaxed">
              Privacy-first billing for the Monero economy.
            </p>
            <a
              href="#deploy"
              className="inline-block mt-6 px-6 py-3 bg-gb-primary hover:bg-gb-primaryHover text-gb-bg font-heading font-bold text-sm rounded-lg transition-colors duration-200"
            >
              DEPLOY NOW
            </a>
          </div>

          {/* Link columns */}
          {Object.entries(links).map(([title, items]) => (
            <div key={title}>
              <h4 className="font-mono text-[11px] text-gb-dim tracking-widest uppercase mb-4">
                {title}
              </h4>
              <ul className="space-y-3">
                {items.map((link) => (
                  <li key={link.label}>
                    <a
                      href={link.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-mono text-sm text-gb-muted hover:text-gb-primary transition-colors duration-200"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      {/* Bottom bar */}
      <div className="border-t border-gb-border">
        <div className="max-w-6xl mx-auto px-6 lg:px-8 py-6 flex flex-col md:flex-row items-center justify-between gap-4">
          <span className="font-mono text-[11px] text-gb-dim">
            © 2026 GhostBill. A Gexiro Enterprises Product. Gibraltar.
          </span>
          <span className="font-mono text-[11px] text-gb-dim">
            AGPL-3.0 Licensed · Open Source
          </span>
        </div>
      </div>
    </footer>
  );
}
