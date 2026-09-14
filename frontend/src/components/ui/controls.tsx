import { useEffect, useId, useRef, useState, type ButtonHTMLAttributes, type KeyboardEvent, type ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import styles from "./ui.module.css";

const cx = (...names: Array<string | false | null | undefined>) => names.filter(Boolean).join(" ");

export function Button({
  variant = "default",
  size = "normal",
  icon,
  iconOnly = false,
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "primary" | "ghost";
  size?: "normal" | "small";
  icon?: IconName;
  iconOnly?: boolean;
}) {
  return (
    <button
      type="button"
      className={cx(styles.button, variant !== "default" && styles[variant], size === "small" && styles.small, iconOnly && styles.icon, className)}
      {...props}
    >
      {icon ? <Icon name={icon} /> : null}
      {children}
    </button>
  );
}

export interface Choice<T extends string | number> {
  value: T;
  label: string;
  description?: string;
  disabled?: boolean;
}

/** A radio group drawn as one control; arrow keys move and select, as in a native radio group. */
export function SegmentedControl<T extends string | number>({
  label,
  choices,
  value,
  onChange,
  disabled = false,
  className,
}: {
  label: string;
  choices: Choice<T>[];
  value: T;
  onChange: (value: T) => void;
  disabled?: boolean;
  className?: string;
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const enabled = choices.filter((c) => !c.disabled && !disabled);

  const onKeyDown = (event: KeyboardEvent) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key];
    if (!step || enabled.length === 0) return;
    event.preventDefault();
    const at = Math.max(enabled.findIndex((c) => c.value === value), 0);
    const next = enabled[(at + step + enabled.length) % enabled.length];
    onChange(next.value);
    refs.current[choices.indexOf(next)]?.focus();
  };

  return (
    <div role="radiogroup" aria-label={label} className={cx(styles.segmented, className)} onKeyDown={onKeyDown}>
      {choices.map((choice, i) => {
        const checked = choice.value === value;
        return (
          <button
            key={String(choice.value)}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            disabled={disabled || choice.disabled}
            title={choice.description}
            className={styles.segment}
            onClick={() => onChange(choice.value)}
          >
            {choice.label}
          </button>
        );
      })}
    </div>
  );
}

/** A custom listbox: the options carry a one-line explanation a native select can't show. */
export function Select<T extends string>({
  label,
  choices,
  value,
  onChange,
}: {
  label: string;
  choices: Choice<T>[];
  value: T;
  onChange: (value: T) => void;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const id = useId();
  const current = choices.find((c) => c.value === value);

  useEffect(() => {
    if (!open) return;
    setActive(Math.max(choices.findIndex((c) => c.value === value), 0));
    list.current?.focus();
    const onPointer = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open, choices, value]);

  const choose = (index: number) => {
    onChange(choices[index].value);
    setOpen(false);
    button.current?.focus();
  };

  const onListKey = (event: KeyboardEvent) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((a) => (a + step + choices.length) % choices.length);
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      setActive(event.key === "Home" ? 0 : choices.length - 1);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      choose(active);
    } else if (event.key === "Escape" || event.key === "Tab") {
      event.stopPropagation();
      setOpen(false);
      if (event.key === "Escape") button.current?.focus();
    }
  };

  return (
    <div className={styles.select} ref={root}>
      <button
        ref={button}
        type="button"
        className={styles.selectButton}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <span className={styles.selectLabel}>{label}</span>
        <span className={styles.selectValue}>{current?.label}</span>
        <Icon name="chevron" />
      </button>
      {open ? (
        <ul
          ref={list}
          id={`${id}-list`}
          role="listbox"
          tabIndex={-1}
          aria-label={label}
          aria-activedescendant={`${id}-${active}`}
          className={styles.listbox}
          onKeyDown={onListKey}
        >
          {choices.map((choice, i) => (
            <li
              key={choice.value}
              id={`${id}-${i}`}
              role="option"
              aria-selected={choice.value === value}
              data-active={i === active}
              className={styles.option}
              onPointerEnter={() => setActive(i)}
              onClick={() => choose(i)}
            >
              <span>{choice.value === value ? <Icon name="check" /> : null}</span>
              <span>{choice.label}</span>
              {choice.description ? <small>{choice.description}</small> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function Chip({ tone, icon, children, title }: { tone?: "ok" | "warn" | "bad"; icon?: IconName; children: ReactNode; title?: string }) {
  return (
    <span className={cx(styles.chip, tone === "ok" && styles.chipOk, tone === "warn" && styles.chipWarn, tone === "bad" && styles.chipBad)} title={title}>
      {icon ? <Icon name={icon} /> : null}
      {children}
    </span>
  );
}

export function Switch({ checked, onChange, children, disabled }: { checked: boolean; onChange: (checked: boolean) => void; children: ReactNode; disabled?: boolean }) {
  return (
    <button type="button" role="switch" aria-checked={checked} className={styles.switch} disabled={disabled} onClick={() => onChange(!checked)}>
      <span className={styles.track} />
      {children}
    </button>
  );
}

/** A collapsible branch of the dissection tree. */
export function Section({ title, meta, open = true, children }: { title: string; meta?: ReactNode; open?: boolean; children: ReactNode }) {
  return (
    <details className={styles.section} open={open}>
      <summary className={styles.summary}>
        <Icon name="chevron" />
        {title}
        {meta ? <span className={styles.meta}>{meta}</span> : null}
      </summary>
      <div className={styles.sectionBody}>{children}</div>
    </details>
  );
}

export function Fields({ children }: { children: ReactNode }) {
  return <dl className={styles.fields}>{children}</dl>;
}

/** A stored value prints as-is; anything the page works out goes in brackets after it. */
export function Field({ name, children, derived }: { name: ReactNode; children: ReactNode; derived?: string }) {
  return (
    <>
      <dt>{name}</dt>
      <dd>
        {children}
        {derived ? <span className={styles.derived}> [{derived}]</span> : null}
      </dd>
    </>
  );
}

export function FieldGroup({ children }: { children: ReactNode }) {
  return <div className={styles.group}>{children}</div>;
}

export function Skeleton({ width = "100%", height }: { width?: string | number; height?: number }) {
  return <span className={styles.skeleton} style={{ width, height }} aria-hidden="true" />;
}
