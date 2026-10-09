import { useRef, type ButtonHTMLAttributes, type KeyboardEvent, type ReactNode } from 'react';
import { initials } from '../lib/format';
import { Icon } from './Icon';

type Variant = 'primary' | 'ghost' | 'quiet' | 'danger';
type Size = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  block?: boolean;
}

export function Spinner({ size = 16 }: { size?: number }) {
  return <span className="spinner" style={{ width: size, height: size }} aria-hidden="true" />;
}

export function Button({ variant = 'ghost', size = 'md', loading, block, className = '', children, disabled, type = 'button', ...rest }: ButtonProps) {
  const cls = ['btn', `btn--${variant}`, size !== 'md' ? `btn--${size}` : '', block ? 'btn--block' : '', className].filter(Boolean).join(' ');
  return (
    <button type={type} className={cls} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading && <Spinner />}
      <span>{children}</span>
    </button>
  );
}

export function Tag({ tone = 'plain', icon, children }: { tone?: 'plain' | 'ok' | 'warn' | 'bad' | 'accent'; icon?: Parameters<typeof Icon>[0]['name']; children: ReactNode }) {
  return (
    <span className={`tag tag--${tone}`}>
      {icon && <Icon name={icon} size={14} />}
      {children}
    </span>
  );
}

export function Avatar({ name }: { name: string }) {
  return <span className="avatar" aria-hidden="true">{initials(name)}</span>;
}

export function Skeleton({ w, h = 16, className = '' }: { w?: number | string; h?: number; className?: string }) {
  return <span className={`sk ${className}`} style={{ width: w ?? '100%', height: h }} aria-hidden="true" />;
}

export function CardSkeleton() {
  return (
    <div className="card card--skeleton" aria-hidden="true">
      <div className="sk sk--poster" />
      <div className="card__body">
        <Skeleton h={24} />
        <Skeleton w="60%" h={16} />
        <Skeleton w="75%" h={16} />
        <Skeleton h={20} w="50%" />
        <Skeleton h={40} />
      </div>
    </div>
  );
}

export function ErrorState({ error, onRetry, title = 'This section did not load' }: { error: Error | undefined; onRetry?: () => void; title?: string }) {
  return (
    <div className="state state--error" role="alert">
      <Icon name="alert" size={20} />
      <div className="state__text">
        <p className="state__title">{title}</p>
        <p className="muted">{error?.message ?? 'Something went wrong.'}</p>
      </div>
      {onRetry && <Button size="sm" onClick={onRetry}>Try again</Button>}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="state">
      <div className="state__text">
        <p className="state__title">{title}</p>
        {children && <p className="muted">{children}</p>}
      </div>
      {action}
    </div>
  );
}

export function Notice({ tone = 'info', children, action }: { tone?: 'info' | 'warn' | 'bad' | 'ok'; children: ReactNode; action?: ReactNode }) {
  return (
    <div className={`notice notice--${tone}`} role={tone === 'bad' ? 'alert' : undefined}>
      <Icon name={tone === 'ok' ? 'check' : tone === 'info' ? 'info' : 'alert'} size={18} />
      <div className="notice__text">{children}</div>
      {action}
    </div>
  );
}

export interface TabDef<T extends string> { id: T; label: string; count?: number }

export function Tabs<T extends string>({ tabs, value, onChange, label }: { tabs: TabDef<T>[]; value: T; onChange: (id: T) => void; label: string }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = tabs.findIndex((t) => t.id === value);
    let n = i;
    if (e.key === 'ArrowRight') n = (i + 1) % tabs.length;
    else if (e.key === 'ArrowLeft') n = (i - 1 + tabs.length) % tabs.length;
    else if (e.key === 'Home') n = 0;
    else if (e.key === 'End') n = tabs.length - 1;
    else return;
    e.preventDefault();
    onChange(tabs[n].id);
    refs.current[n]?.focus();
  };
  return (
    <div className="tabs" role="tablist" aria-label={label} onKeyDown={onKey}>
      {tabs.map((t, i) => (
        <button
          key={t.id}
          ref={(el) => { refs.current[i] = el; }}
          type="button"
          role="tab"
          id={`tab-${t.id}`}
          aria-selected={t.id === value}
          tabIndex={t.id === value ? 0 : -1}
          className="tab"
          onClick={() => onChange(t.id)}
        >
          {t.label}
          {t.count !== undefined && <span className="tab__count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function PageHead({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="pagehead">
      <div className="pagehead__text">
        <h1 className="pagehead__title">{title}</h1>
        {sub && <p className="pagehead__sub">{sub}</p>}
      </div>
      {actions && <div className="pagehead__actions">{actions}</div>}
    </header>
  );
}

export function Field({ id, label, hint, error, children }: { id: string; label: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>{label}</label>
      {children}
      {error ? <p className="field__error" id={`${id}-err`} role="alert">{error}</p> : hint ? <p className="field__hint" id={`${id}-hint`}>{hint}</p> : null}
    </div>
  );
}
