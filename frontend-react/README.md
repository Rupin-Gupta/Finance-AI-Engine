# Finance AI Console (React + Tailwind + TypeScript)

A production-grade analyst console for the AI Financial Decision Engine. Talks only to the
existing FastAPI `/v1/*` surface (no direct DB) — the same separation as the Streamlit UI.

**Aesthetic:** *After-Hours Terminal* — near-black canvas, one amber signal accent, and every
number in tabular monospace. Full design system, navigation architecture, wireframes, UX review
and usability risks are in [`DESIGN.md`](./DESIGN.md).

## Sections
Overview · Portfolio Analysis · AI Recommendations · Risk Analysis · Backtesting · Market Signals · Reports · Settings.

## Accessibility
Skip-to-content link · semantic landmarks (`header`/`nav`/`main`) · `aria-current` nav · visible
`:focus-visible` rings · labeled inputs · color-never-alone (glyph + text on every BUY/SELL/HOLD) ·
44px touch targets · `prefers-reduced-motion` honored · contrast ≥ 4.5:1 (primary ~13:1).

## Run

```bash
cd frontend-react
npm install
npm run dev        # http://localhost:5173  (proxies /v1 → http://localhost:8000)
```

Open **Settings** → set the API base URL (e.g. `http://localhost:8000`) and your `X-API-Key`,
then **Test connection**. In dev the Vite proxy forwards `/v1` to `:8000`, so a blank base works.

```bash
npm run typecheck   # tsc --noEmit
npm run build       # tsc -b && vite build  → dist/  (route-level code-split)
npm run preview     # serve the production build
```

## Stack
Vite · React 18 · TypeScript (strict) · Tailwind v3 (CSS-variable tokens) · react-router · recharts · lucide-react.

## Structure
```
src/
├── lib/        api (typed /v1 client), types, format, useAsync
├── components/ AppShell (accessible nav), ui (Card/Stat/RecBadge/ConfidenceBar/states)
└── pages/      Overview, Portfolio, Recommendations, Risk, Backtesting, Signals, Reports, Settings
```

> This is the React migration (roadmap **P13**). The Streamlit dashboard in `frontend/` still
> works against the same API; both are interchangeable clients.
