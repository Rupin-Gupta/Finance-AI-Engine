import type { ReactNode } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import type { Rec } from "../lib/types";

/* ---- Card ---------------------------------------------------------------- */
export function Card({
  title,
  action,
  children,
  className = "",
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card p-4 ${className}`}>
      {(title || action) && (
        <header className="mb-3 flex items-center justify-between">
          {title && <h3 className="text-sm font-semibold text-text">{title}</h3>}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

/* ---- KPI stat ------------------------------------------------------------ */
export function Stat({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "default" | "bull" | "bear" | "accent" | "muted" | "neutral";
}) {
  const toneClass = {
    default: "text-text",
    bull: "text-bull",
    bear: "text-bear",
    accent: "text-accent",
    muted: "text-muted",
    neutral: "text-neutral",
  }[tone];
  return (
    <div className="card p-4">
      <div className="text-2xs font-semibold uppercase tracking-wide text-muted">{label}</div>
      <div className={`num mt-1 text-xl font-semibold ${toneClass}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </div>
  );
}

/* ---- Recommendation badge (color + glyph + label, never color alone) ----- */
const REC_META: Record<Rec, { cls: string; glyph: string }> = {
  BUY: { cls: "border-bull/40 bg-bull/10 text-bull", glyph: "▲" },
  SELL: { cls: "border-bear/40 bg-bear/10 text-bear", glyph: "▼" },
  HOLD: { cls: "border-neutral/40 bg-neutral/10 text-neutral", glyph: "■" },
};
export function RecBadge({ rec, size = "sm" }: { rec: Rec; size?: "sm" | "lg" }) {
  const m = REC_META[rec];
  return (
    <span
      className={`chip ${m.cls} ${size === "lg" ? "px-3 py-1 text-sm" : ""}`}
      role="status"
      aria-label={`Recommendation: ${rec}`}
    >
      <span aria-hidden>{m.glyph}</span>
      {rec}
    </span>
  );
}

/* ---- Confidence "spine" + bar ------------------------------------------- */
export function ConfidenceBar({ value }: { value: number }) {
  const pctv = Math.round(value * 100);
  return (
    <div
      className="flex items-center gap-2"
      role="meter"
      aria-valuenow={pctv}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Confidence"
    >
      <div className="h-2 w-28 overflow-hidden rounded-full border bg-bg">
        <div className="h-full rounded-full bg-accent" style={{ width: `${pctv}%` }} />
      </div>
      <span className="num text-sm text-text">{pctv}%</span>
    </div>
  );
}

/* ---- Chips for severity / regime ---------------------------------------- */
export function Chip({ children, tone = "muted" }: { children: ReactNode; tone?: string }) {
  const map: Record<string, string> = {
    muted: "border-border text-muted",
    accent: "border-accent/40 bg-accent/10 text-accent",
    bull: "border-bull/40 bg-bull/10 text-bull",
    bear: "border-bear/40 bg-bear/10 text-bear",
    neutral: "border-neutral/40 bg-neutral/10 text-neutral",
  };
  return <span className={`chip ${map[tone] ?? map.muted}`}>{children}</span>;
}

/* ---- States -------------------------------------------------------------- */
export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-8 text-sm text-muted" role="status" aria-live="polite">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div
      className="flex items-start gap-2 rounded-md border border-bear/40 bg-bear/10 p-3 text-sm text-bear"
      role="alert"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span>{message}</span>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="py-8 text-center text-sm text-muted">{children}</div>;
}

/* ---- Async section wrapper ---------------------------------------------- */
export function AsyncBlock<T>({
  state,
  empty,
  children,
}: {
  state: { data: T | null; loading: boolean; error: string | null };
  empty?: ReactNode;
  children: (data: T) => ReactNode;
}) {
  if (state.loading) return <Loading />;
  if (state.error) return <ErrorState message={state.error} />;
  if (!state.data) return <>{empty ?? <Empty>No data yet.</Empty>}</>;
  return <>{children(state.data)}</>;
}
