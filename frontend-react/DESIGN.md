# Finance AI Engine — Frontend Design

Design + build of a React/Tailwind/TypeScript console for the AI Financial Decision Engine.
Audience: **retail investors, financial analysts, wealth managers**. Goals: trustworthy,
professional, data-focused, accessible, fast to navigate.

---

## 1. Design Direction

**Aesthetic name:** *After-Hours Terminal* — the calm authority of a professional trading
terminal, modernized. Near-black canvas, generous data density, and **every number set in a
monospaced tabular face** so figures align to the decimal and read as precise instruments,
not marketing copy.

**Differentiation anchor:** numerics. Prices, percentages, confidence, VaR, Sharpe — all
`IBM Plex Mono`, tabular-aligned, with a thin **conviction "spine"** (a vertical signal meter)
on every recommendation. Screenshot it with the logo removed and you'd still know it's a
serious analyst tool, not a generic SaaS dashboard.

**Tone:** Industrial / Utilitarian + a restrained Editorial header rhythm. Two directions, no more.

**DFII score:** Impact 4 + Fit 5 + Feasibility 4 + Performance 4 − Consistency-risk 2 = **15 / 15 (Execute fully)**.
Token-driven so consistency risk stays low across 8 sections.

**Avoids generic UI by:** committing to monospaced tabular numerics + a single amber "signal"
accent on a near-black canvas, instead of the default blue/purple-on-white SaaS gradient.

---

## 2. Design System

### Type
- **Display / headings:** `Space Grotesk` — technical, geometric, distinctive (not Inter/Roboto).
- **Body / UI:** `IBM Plex Sans` — humanist, trustworthy, screen-legible at 14–16px.
- **Numerics / code / tables:** `IBM Plex Mono` (`font-variant-numeric: tabular-nums`) — the anchor.
- Scale (1.25 ratio): 12 / 14 / 16 / 20 / 25 / 31 / 39 px. Body 14–16, line-height 1.5–1.6.

### Color (CSS variables, dark-first)
| Token | Hex | Use |
|-------|-----|-----|
| `--bg` | `#0B0E13` | app canvas (after-hours) |
| `--surface` | `#121722` | cards / panels |
| `--surface-2` | `#1A2130` | raised / hover rows |
| `--border` | `#232C3B` | hairline dividers |
| `--text` | `#E6EDF3` | primary text (contrast ≥ 13:1 on bg) |
| `--text-muted` | `#9AA7B8` | secondary (contrast ≥ 5.4:1) |
| `--accent` | `#F5B301` | **signal/attention** (amber-gold) |
| `--bull` | `#22C55E` | BUY / up / low-risk |
| `--bear` | `#F0556B` | SELL / down / high-risk |
| `--neutral` | `#C9A227` | HOLD / caution |
| `--info` | `#5AA2F0` | links / focus ring |

One dominant tone (slate-black), one accent (amber), one neutral system. Semantics never rely
on color alone — every BUY/SELL/HOLD also carries a glyph + label.

### Spacing & layout
- 4px rhythm (4/8/12/16/24/32/48). Dense by intent — KPI cards `p-4`, tables tight rows.
- Max content width `max-w-[1440px]`; fixed left rail (256px) + fluid main.
- Radius: 8px cards, 6px controls. Borders are 1px hairlines, never heavy shadows.

### Motion
- 150–200ms `transform`/`opacity` only; row highlight + tooltip + chart hover.
- One entrance: content fades/translates 8px on route change. `prefers-reduced-motion` → none.

### Iconography
- **Lucide SVG icons** (no emoji as UI icons). 20px, `stroke-width:1.75`, currentColor.

---

## 3. Navigation Architecture

Persistent **left rail** (primary, 8 sections) + **top bar** (global symbol search, env/health,
API-key status). Flat IA — every section one click deep; details open in-page panels, not nested routes.

```
Top bar:  [logo]  [⌘K symbol search]            [market: US bull / IN bear]  [● API ok]
Left rail (aria nav, aria-current):
  ▸ Overview          /                 market pulse, regime, top signals, alerts
  ▸ Portfolio         /portfolio        holdings, live P&L, allocation, sizing
  ▸ AI Recommendations /recommendations decision cards, committee, confidence
  ▸ Risk Analysis     /risk             VaR/CVaR, concentration, correlation, stops
  ▸ Backtesting       /backtesting      cost-realistic replay, equity curve
  ▸ Market Signals    /signals          regime, events, India flow, calibration/drift
  ▸ Reports           /reports          AI sector reports, generate, history
  ▸ Settings          /settings         API base/key, theme, defaults
```

Keyboard model: `Tab` order = visual order; `g then o/p/r/...` optional jump; `⌘K`/`/` focuses
symbol search; `Esc` closes panels. `aria-current="page"` on the active rail item.

---

## 4. Wireframes (ASCII)

**Overview**
```
┌ Top bar ─────────────────────────────────────────────────────────────┐
├ rail ┬ ───────────────────────────────────────────────────────────── ┤
│ Over │  Market Pulse                                                   │
│ Port │  ┌ US: BULL ┐ ┌ India: BEAR ┐ ┌ Open Alerts: 4 ┐ ┌ Models ✓ ┐  │
│ Recs │  └──────────┘ └─────────────┘ └────────────────┘ └──────────┘  │
│ Risk │  Top Signals (today)                  Recent Alerts            │
│ Back │  ┌───────────────────────────┐        ┌───────────────────┐    │
│ Sig  │  │ AAPL  ▌ SELL  conf 60%    │        │ ⚠ NVDA stop break │    │
│ Rep  │  │ MSFT  ▌ HOLD  conf 48%    │        │ ⚠ AAPL stale data │    │
│ Set  │  │ ...   (sortable table)    │        │ ⚠ model drift     │    │
└──────┴──┴───────────────────────────┴────────┴───────────────────┴────┘
```

**AI Recommendations (detail)**
```
 Symbol ▢ AAPL  [Analyze]
 ┌ Decision ────────────────────────────────────────────────┐
 │ ▌ SELL    conf 60% ████████░░   risk: Medium   regime BULL │
 │ spine     event gate: FOMC 1d (≤0.60)                      │
 │ Sizing  suggested 0.0%  · Kelly 0% · vol-tgt 4% · risk 3%  │
 ├ Signal scorecard (8 + overlays) ──────────────────────────┤
 │ RSI ●  Trend ●  Momentum ●  Vol ●  Sentiment ●  Forecast ● │
 ├ Committee  [Convene] ─────────────────────────────────────┤
 │ Tech HOLD · Fund BUY · Macro BUY · Sent HOLD → endorses    │
 └────────────────────────────────────────────────────────────┘
```

**Risk Analysis**
```
 Source ( watchlist | paper )   [Analyze]
 ┌ Risk Score  Medium 38/100 ┐  ┌ VaR95 1.6% ┐ ┌ CVaR 2.5% ┐ ┌ Corr .12 ┐
 Sector donut + country/cap exposure        Stop-Loss monitor (breaches ▲)
```

---

## 5. UX Review (against the 99-guideline checklist)

- **Accessibility (CRITICAL):** semantic landmarks (`header/nav/main`), skip-to-content link,
  `aria-current` nav, `aria-label` on icon-only buttons, labeled inputs, `:focus-visible` rings
  (info-blue, 2px), color never the sole signal (glyph+text), `prefers-reduced-motion` honored.
  Text contrast ≥ 4.5:1 (primary ~13:1, muted ~5.4:1).
- **Touch & interaction:** 44px targets, `cursor-pointer` on actionables, async buttons disable +
  show spinner, errors render inline near the control.
- **Performance:** route-level code-splitting, charts lazy, reserved skeleton space (no layout
  jump), fonts subset + `display=swap`.
- **Layout/responsive:** rail collapses to a top drawer < 768px; tables scroll-x in a bounded
  container; tested 375/768/1024/1440.
- **Data viz:** match chart to data — line (equity curve, drift), bar (signal scores, sentiment),
  donut (allocation), scatter (efficient frontier). Every chart has a table fallback + aria summary.

## 6. Usability Risks (and mitigations)

| Risk | Why it bites this product | Mitigation |
|------|---------------------------|------------|
| **Overconfidence in AI** | retail users may treat a recommendation as advice | always show confidence + risk + the gates that capped it; "not financial advice" footer; committee veto surfaced |
| **Data staleness misread** | a stale price looks live | P9 data-quality badge on any symbol with stale/divergent data |
| **Dark-mode contrast traps** | muted-on-dark can fail AA | tokens pre-checked ≥ 4.5:1; never gray-on-gray for body |
| **Density → cognitive overload** | 8 signals + overlays + committee | progressive disclosure: scorecard first, committee/timeframes/backtest behind explicit actions |
| **Empty/late states** | jobs may not have run | every panel has empty + loading + error states with a next-step hint |
| **Keyboard traps in panels** | modals/expanders | focus trap + `Esc` to close + return focus to trigger |
| **Number misalignment** | ragged decimals erode trust | tabular-nums mono everywhere numbers appear |

---

## 7. Stack & Structure

Vite + React 18 + TypeScript + Tailwind v3 + react-router + recharts + lucide-react.
Talks only to the existing FastAPI `/v1/*` (no direct DB), API base + key from Settings (localStorage).
See `src/` — tokens in `index.css` + `tailwind.config.ts`, typed client in `src/lib/`.
