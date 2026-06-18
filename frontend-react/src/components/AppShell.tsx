import { useEffect, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  Activity,
  BarChart3,
  Briefcase,
  CircleDot,
  FileText,
  Gauge,
  LayoutDashboard,
  Menu,
  Radar,
  Settings,
  Sparkles,
  X,
} from "lucide-react";
import type { ReactNode } from "react";
import { api } from "../lib/api";
import type { RegimeResponse } from "../lib/types";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/portfolio", label: "Portfolio", icon: Briefcase },
  { to: "/recommendations", label: "AI Recommendations", icon: Sparkles },
  { to: "/risk", label: "Risk Analysis", icon: Gauge },
  { to: "/backtesting", label: "Backtesting", icon: BarChart3 },
  { to: "/signals", label: "Market Signals", icon: Radar },
  { to: "/reports", label: "Reports", icon: FileText },
  { to: "/settings", label: "Settings", icon: Settings },
];

function HealthDot() {
  const [ok, setOk] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    api
      .get<{ status: string }>("/ready")
      .then(() => alive && setOk(true))
      .catch(() => alive && setOk(false));
    return () => {
      alive = false;
    };
  }, []);
  const tone = ok === null ? "text-muted" : ok ? "text-bull" : "text-bear";
  const label = ok === null ? "checking" : ok ? "API ok" : "API down";
  return (
    <span className={`flex items-center gap-1.5 text-xs ${tone}`} aria-live="polite">
      <CircleDot className="h-3.5 w-3.5" aria-hidden /> {label}
    </span>
  );
}

function RegimeTag() {
  const [r, setR] = useState<RegimeResponse | null>(null);
  useEffect(() => {
    api.get<RegimeResponse>("/v1/regime").then(setR).catch(() => void 0);
  }, []);
  if (!r) return null;
  const fmt = (x: { regime: string } | null) => (x ? x.regime.replace("_", "-") : "—");
  return (
    <span className="hidden items-center gap-1 text-xs text-muted md:flex">
      <Activity className="h-3.5 w-3.5" aria-hidden />
      US <b className="text-text">{fmt(r.us)}</b> · IN <b className="text-text">{fmt(r.india)}</b>
    </span>
  );
}

export default function AppShell({
  children,
  symbol,
  setSymbol,
}: {
  children: ReactNode;
  symbol: string;
  setSymbol: (s: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(symbol);
  const navigate = useNavigate();
  useEffect(() => setDraft(symbol), [symbol]);

  function submitSymbol(e: React.FormEvent) {
    e.preventDefault();
    const s = draft.trim().toUpperCase();
    if (s) {
      setSymbol(s);
      navigate("/recommendations");
      setOpen(false);
    }
  }

  return (
    <div className="min-h-screen bg-bg text-text">
      <a href="#main" className="skip-link">
        Skip to content
      </a>

      {/* Top bar */}
      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b bg-surface/95 px-4 backdrop-blur">
        <button
          className="btn px-2 md:hidden"
          aria-label={open ? "Close navigation" : "Open navigation"}
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
        <div className="flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-md bg-accent font-display text-sm font-bold text-bg">
            F
          </span>
          <span className="font-display text-sm font-semibold tracking-tight">
            Finance<span className="text-accent">AI</span> Console
          </span>
        </div>
        <form onSubmit={submitSymbol} className="ml-auto flex items-center gap-2" role="search">
          <label htmlFor="symbol-search" className="sr-only">
            Symbol search
          </label>
          <input
            id="symbol-search"
            className="input w-32 sm:w-44"
            placeholder="Symbol (AAPL)"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
          <button type="submit" className="btn btn-accent">
            Analyze
          </button>
        </form>
        <div className="ml-3 hidden items-center gap-4 lg:flex">
          <RegimeTag />
          <HealthDot />
        </div>
      </header>

      <div className="mx-auto flex max-w-content">
        {/* Left rail */}
        <nav
          aria-label="Primary"
          className={`${
            open ? "block" : "hidden"
          } fixed inset-x-0 top-14 z-20 border-b bg-surface md:static md:block md:w-64 md:shrink-0 md:border-b-0 md:border-r`}
        >
          <ul className="p-3 md:sticky md:top-14">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={end}
                  onClick={() => setOpen(false)}
                  className={({ isActive }) =>
                    `mb-0.5 flex min-h-[44px] items-center gap-3 rounded-md px-3 text-sm transition-colors ${
                      isActive
                        ? "bg-surface-2 font-semibold text-text"
                        : "text-muted hover:bg-surface-2 hover:text-text"
                    }`
                  }
                  aria-current={undefined}
                >
                  {({ isActive }) => (
                    <span
                      className="flex items-center gap-3"
                      aria-current={isActive ? "page" : undefined}
                    >
                      <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden />
                      {label}
                    </span>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        {/* Main */}
        <main id="main" className="min-w-0 flex-1 animate-fade-up p-4 sm:p-6" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}
