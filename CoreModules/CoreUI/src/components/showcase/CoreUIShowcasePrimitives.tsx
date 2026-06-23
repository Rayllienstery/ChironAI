import type { ReactNode } from 'react';

export const sourceRoot = 'src';

export function CodePill({ children }: { children: ReactNode }) {
  return <code className="coreui-showcase-code-pill">{children}</code>;
}

type ShowcaseItemProps = {
  name: string;
  classes: string[];
  source: string;
  description: string;
  children: ReactNode;
};

export function ShowcaseItem({ name, classes, source, description, children }: ShowcaseItemProps) {
  return (
    <article className="coreui-showcase-item">
      <div className="coreui-showcase-preview">{children}</div>
      <div className="coreui-showcase-meta">
        <div>
          <span className="coreui-showcase-kicker">Internal name</span>
          <h3>{name}</h3>
        </div>
        <p>{description}</p>
        <div className="coreui-showcase-meta-row">
          <span>CSS</span>
          <div className="coreui-showcase-code-list">
            {classes.map((className) => (
              <CodePill key={className}>{className}</CodePill>
            ))}
          </div>
        </div>
        <div className="coreui-showcase-meta-row">
          <span>Source</span>
          <CodePill>{source}</CodePill>
        </div>
      </div>
    </article>
  );
}

export function ShowcaseSection({ title, children }: { title: string; children: ReactNode }) {
  const id = `coreui-showcase-${title.toLowerCase().replaceAll(' ', '-')}`;
  return (
    <section className="coreui-showcase-section" aria-labelledby={id}>
      <div className="coreui-showcase-section-header">
        <h2 id={id}>{title}</h2>
      </div>
      <div className="coreui-showcase-list">{children}</div>
    </section>
  );
}

export function TokenSwatch({
  label,
  token,
  className = '',
}: {
  label: string;
  token: string;
  className?: string;
}) {
  return (
    <div className={['coreui-showcase-token', className].filter(Boolean).join(' ')}>
      <span className="coreui-showcase-token-swatch" style={{ background: `var(${token})` }} />
      <span>{label}</span>
      <CodePill>{token}</CodePill>
    </div>
  );
}

export function FontCard({
  title,
  token,
  description,
  sampleClassName,
  sample,
}: {
  title: string;
  token: string;
  description: string;
  sampleClassName?: string;
  sample: ReactNode;
}) {
  return (
    <article className="coreui-showcase-font-card">
      <h4>{title}</h4>
      <span className={['coreui-showcase-font-card-sample', sampleClassName].filter(Boolean).join(' ')}>
        {sample}
      </span>
      <p>{description}</p>
      <CodePill>{token}</CodePill>
    </article>
  );
}

export const SHOWCASE_SUBTABS = [
  { id: 'colors', label: 'Colors and fonts' },
  { id: 'buttons', label: 'Buttons' },
  { id: 'cards', label: 'Cards' },
  { id: 'components', label: 'Components' },
  { id: 'layout', label: 'Layout & Navigation' },
  { id: 'data', label: 'Data & Feedback' },
  { id: 'icons', label: 'Icons' },
  { id: 'notifications', label: 'Notifications' },
] as const;
