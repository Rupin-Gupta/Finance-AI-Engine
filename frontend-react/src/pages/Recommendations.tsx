import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import type { Committee, Decision } from "../lib/types";
import {
  AsyncBlock,
  Card,
  Chip,
  ConfidenceBar,
  ErrorState,
  Loading,
  RecBadge,
} from "../components/ui";
import { pct, signedPct, titleCase } from "../lib/format";

const SIGNAL_LABELS: Record<string, string> = {
  rsi: "RSI",
  trend: "Trend",
  momentum: "Momentum",
  volatility: "Volatility",
  sentiment: "Sentiment",
  forecast: "Forecast",
  ema_crossover: "EMA Cross",
  volume: "Volume",
  india_flow: "India Flow",
  ml: "ML Model",
};

function SignalCell({ name, score, value }: { name: string; score: number; value: number | null }) {
  const tone = score > 0 ? "text-bull" : score < 0 ? "text-bear" : "text-muted";
  const glyph = score > 0 ? "▲" : score < 0 ? "▼" : "■";
  return (
    <div className="rounded-md border bg-bg p-2">
      <div className="text-2xs font-semibold uppercase tracking-wide text-muted">
        {SIGNAL_LABELS[name] ?? titleCase(name)}
      </div>
      <div className={`num mt-0.5 text-sm font-semibold ${tone}`}>
        <span aria-hidden>{glyph}</span> {score > 0 ? "+" : ""}
        {score.toFixed(1)}
      </div>
      <div className="num text-2xs text-muted">{value === null ? "—" : value.toFixed(2)}</div>
    </div>
  );
}

export default function Recommendations({ symbol }: { symbol: string }) {
  const [committee, setCommittee] = useState<Committee | null>(null);
  const [comLoading, setComLoading] = useState(false);
  const [comError, setComError] = useState<string | null>(null);

  const decision = useAsync<Decision>(
    useCallback(() => api.get(`/v1/decision/${encodeURIComponent(symbol)}`), [symbol]),
  );

  // Load decision whenever the active symbol changes.
  useEffect(() => {
    setCommittee(null);
    setComError(null);
    void decision.run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol]);

  async function convene() {
    setComLoading(true);
    setComError(null);
    try {
      setCommittee(await api.get<Committee>(`/v1/decision/${encodeURIComponent(symbol)}/committee`));
    } catch (e) {
      setComError(e instanceof Error ? e.message : String(e));
    } finally {
      setComLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">AI Recommendations</h1>
          <p className="text-sm text-muted">
            Engine verdict for <span className="font-mono text-text">{symbol}</span> — search any
            symbol in the top bar.
          </p>
        </div>
        <button className="btn" onClick={() => decision.run()} disabled={decision.loading}>
          {decision.loading ? "Refreshing…" : "Refresh"}
        </button>
      </header>

      <AsyncBlock state={decision}>
        {(d) => (
          <div className="space-y-4">
            {/* Verdict */}
            <Card>
              <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
                <RecBadge rec={d.recommendation} size="lg" />
                <div>
                  <div className="text-2xs uppercase tracking-wide text-muted">Confidence</div>
                  <ConfidenceBar value={d.confidence} />
                </div>
                <div>
                  <div className="text-2xs uppercase tracking-wide text-muted">Risk</div>
                  <div className="text-sm font-semibold">{d.risk_level}</div>
                </div>
                {d.market_regime && (
                  <Chip tone="accent">Regime: {titleCase(d.market_regime)}</Chip>
                )}
                {d.current_close != null && (
                  <div className="num ml-auto text-right">
                    <div className="text-2xs uppercase tracking-wide text-muted">Price</div>
                    <div className="text-lg font-semibold">{d.current_close.toFixed(2)}</div>
                  </div>
                )}
              </div>

              {d.upcoming_event && (
                <div className="mt-3 flex items-center gap-2 rounded-md border border-accent/40 bg-accent/10 p-2 text-sm text-accent">
                  ⚠ {d.upcoming_event.title} in {d.upcoming_event.days_to_event}d (
                  {d.upcoming_event.impact}) — confidence gated
                </div>
              )}

              {d.position_sizing && (
                <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {[
                    ["Suggested", d.position_sizing.recommended_pct],
                    ["Kelly", d.position_sizing.kelly_pct],
                    ["Vol-target", d.position_sizing.vol_target_pct],
                    ["Risk-budget", d.position_sizing.risk_budget_pct],
                  ].map(([label, v]) => (
                    <div key={label as string} className="rounded-md border bg-bg p-2">
                      <div className="text-2xs uppercase tracking-wide text-muted">{label}</div>
                      <div className="num text-sm font-semibold">{pct(v as number | undefined)}</div>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            {/* Signal scorecard */}
            <Card title="Signal Scorecard">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-5">
                {Object.entries(d.signals).map(([name, s]) => (
                  <SignalCell key={name} name={name} score={s.score} value={s.value} />
                ))}
              </div>
              <p className="mt-3 text-xs text-muted">
                Weighted score{" "}
                <span className="num text-text">{signedPct(d.weighted_score, 0)}</span> · BUY ≥ 30% ·
                SELL ≤ −30%. Sentiment{" "}
                <span className="num text-text">
                  {d.sentiment_score === null ? "—" : d.sentiment_score.toFixed(2)}
                </span>
                .
              </p>
            </Card>

            {/* Bull / Bear / Synthesis */}
            {(d.bull_case || d.bear_case || d.explanation) && (
              <div className="grid gap-4 lg:grid-cols-3">
                <Card title="Bull Case">
                  <p className="text-sm text-muted">{d.bull_case || "—"}</p>
                </Card>
                <Card title="Bear Case">
                  <p className="text-sm text-muted">{d.bear_case || "—"}</p>
                </Card>
                <Card title="Synthesis">
                  <p className="text-sm text-muted">{d.explanation || "—"}</p>
                </Card>
              </div>
            )}

            {/* Committee */}
            <Card
              title="Investment Committee"
              action={
                <button className="btn btn-accent" onClick={convene} disabled={comLoading}>
                  {comLoading ? "Deliberating…" : "Convene"}
                </button>
              }
            >
              {comLoading && <Loading label="5 agents deliberating…" />}
              {comError && <ErrorState message={comError} />}
              {!comLoading && !comError && !committee && (
                <p className="text-sm text-muted">
                  4 specialists (Technical / Fundamental / Macro / Sentiment) in parallel + a Risk
                  Officer with deterministic veto.
                </p>
              )}
              {committee && committee.llm_available === false && (
                <div className="rounded-md border border-accent/40 bg-accent/10 p-2 text-sm text-accent">
                  ⚠ Committee LLM unavailable (rate-limited or offline) — agents did not respond.
                  Retry in ~60s. Deterministic risk gate:{" "}
                  {committee.vetoed ? `VETO → HOLD (${committee.veto_reasons.join("; ")})` : "no veto"}.
                </div>
              )}
              {committee && committee.llm_available !== false && (
                <div className="space-y-3">
                  {committee.vetoed ? (
                    <div className="rounded-md border border-bear/40 bg-bear/10 p-2 text-sm text-bear">
                      🛑 Risk Officer veto — engine {committee.engine_recommendation} →{" "}
                      <b>{committee.final_recommendation}</b>
                      {committee.veto_reasons.length > 0 && (
                        <span className="text-muted"> ({committee.veto_reasons.join("; ")})</span>
                      )}
                    </div>
                  ) : (
                    <div className="rounded-md border border-bull/40 bg-bull/10 p-2 text-sm text-bull">
                      ✓ Committee endorses <b>{committee.final_recommendation}</b>
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    {Object.entries(committee.votes).map(([role, v]) => (
                      <div key={role} className="rounded-md border bg-bg p-2 text-center">
                        <div className="text-2xs uppercase tracking-wide text-muted">{role}</div>
                        <div className="text-sm font-semibold">{v ?? "—"}</div>
                      </div>
                    ))}
                  </div>
                  {committee.risk_officer && (
                    <details className="rounded-md border bg-bg p-2">
                      <summary className="cursor-pointer text-sm font-medium">Risk Officer</summary>
                      <p className="mt-2 text-sm text-muted">{committee.risk_officer}</p>
                    </details>
                  )}
                </div>
              )}
            </Card>
          </div>
        )}
      </AsyncBlock>
    </div>
  );
}
