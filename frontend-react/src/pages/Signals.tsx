import { useCallback } from "react";
import { api } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import type {
  DriftResponse,
  EventsResponse,
  IndiaSignals,
  MlModelResponse,
  RegimeResponse,
} from "../lib/types";
import { AsyncBlock, Card, Chip, Empty, Stat } from "../components/ui";
import { pct, signedPct, titleCase } from "../lib/format";

const impactTone = (i: string) => (i === "high" ? "bear" : i === "medium" ? "accent" : "muted");
const driftTone = (v: string) =>
  v === "healthy" ? "bull" : v === "degrading" ? "accent" : v === "retraining_recommended" ? "bear" : "muted";

export default function Signals() {
  const regime = useAsync<RegimeResponse>(useCallback(() => api.get("/v1/regime"), []), true);
  const events = useAsync<EventsResponse>(useCallback(() => api.get("/v1/events?days=60"), []), true);
  const india = useAsync<IndiaSignals>(useCallback(() => api.get("/v1/india/signals"), []), true);
  const drift = useAsync<DriftResponse>(useCallback(() => api.get("/v1/calibration/drift"), []), true);
  const ml = useAsync<MlModelResponse>(useCallback(() => api.get("/v1/ml/model"), []), true);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Market Signals</h1>
        <p className="text-sm text-muted">
          Regime, macro events, India flow, and the self-learning loop's health.
        </p>
      </header>

      {/* Regime */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {(["us", "india"] as const).map((m) => (
          <Card key={m} title={m === "us" ? "US Market Regime" : "India Market Regime"}>
            <AsyncBlock state={regime} empty={<Empty>Run regime_run.</Empty>}>
              {(d) => {
                const r = d[m];
                if (!r) return <Empty>No regime yet.</Empty>;
                return (
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <div className="font-display text-xl font-semibold">{titleCase(r.regime)}</div>
                      <div className="text-xs text-muted">{r.reason}</div>
                    </div>
                    <dl className="num text-right text-sm">
                      <div>
                        <dt className="inline text-muted">VIX </dt>
                        <dd className="inline">{r.vix?.toFixed(1) ?? "—"}</dd>
                      </div>
                      <div>
                        <dt className="inline text-muted">Breadth </dt>
                        <dd className="inline">{pct(r.breadth_pct, 0)}</dd>
                      </div>
                    </dl>
                  </div>
                );
              }}
            </AsyncBlock>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Macro events */}
        <Card title="Upcoming Macro Events">
          <AsyncBlock state={events} empty={<Empty>No events.</Empty>}>
            {(d) =>
              d.events.length === 0 ? (
                <Empty>None scheduled.</Empty>
              ) : (
                <ul className="space-y-2">
                  {d.events.slice(0, 8).map((e, i) => (
                    <li key={i} className="flex items-center justify-between gap-2 text-sm">
                      <span className="flex items-center gap-2">
                        <Chip tone={impactTone(e.impact)}>{e.impact}</Chip>
                        {e.title}
                      </span>
                      <time className="num text-2xs text-muted" dateTime={e.date}>
                        {e.date}
                      </time>
                    </li>
                  ))}
                </ul>
              )
            }
          </AsyncBlock>
        </Card>

        {/* India flow */}
        <Card title="India Flow (FII/DII · PCR · Gift Nifty)">
          <AsyncBlock state={india} empty={<Empty>No India data.</Empty>}>
            {(d) => (
              <div className="space-y-3">
                <div className="grid grid-cols-3 gap-2">
                  <Stat label="FII ₹cr" value={d.fii_net_cr?.toFixed(0) ?? "—"} />
                  <Stat label="DII ₹cr" value={d.dii_net_cr?.toFixed(0) ?? "—"} />
                  <Stat label="PCR" value={d.pcr?.toFixed(2) ?? "—"} />
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <Chip tone={d.india_flow.score > 0 ? "bull" : d.india_flow.score < 0 ? "bear" : "muted"}>
                    india_flow {d.india_flow.score > 0 ? "+" : ""}
                    {d.india_flow.score}
                  </Chip>
                  <span className="text-muted">
                    source {d.source ?? "—"} · {d.date ?? "no data"}
                  </span>
                </div>
              </div>
            )}
          </AsyncBlock>
        </Card>

        {/* Model health / drift */}
        <Card title="Model Health (Drift)">
          <AsyncBlock state={drift} empty={<Empty>Not enough history.</Empty>}>
            {(d) => (
              <div className="space-y-2">
                <Chip tone={driftTone(d.verdict)}>{titleCase(d.verdict)}</Chip>
                <div className="grid grid-cols-3 gap-2 text-sm">
                  <Stat label="Recent" value={d.drift.recent ? pct(d.drift.recent.hit_rate, 0) : "—"} />
                  <Stat label="Baseline" value={d.drift.baseline ? pct(d.drift.baseline.hit_rate, 0) : "—"} />
                  <Stat
                    label="Delta"
                    value={signedPct(d.drift.delta)}
                    tone={(d.drift.delta ?? 0) < 0 ? "bear" : "bull"}
                  />
                </div>
                <p className="text-xs text-muted">{d.evaluated_count} evaluable decisions.</p>
              </div>
            )}
          </AsyncBlock>
        </Card>

        {/* ML model */}
        <Card title="ML Directional Model">
          <AsyncBlock state={ml} empty={<Empty>No model.</Empty>}>
            {(d) =>
              !d.latest ? (
                <Empty>No model trained yet.</Empty>
              ) : (
                <div className="space-y-2 text-sm">
                  <Chip tone={d.in_use ? "bull" : "muted"}>
                    {d.in_use ? "Active" : "Not promoted"}
                  </Chip>
                  <div className="grid grid-cols-3 gap-2">
                    <Stat label="OOS AUC" value={d.latest.oos_auc ?? "—"} />
                    <Stat label="Hit rate" value={d.latest.oos_hit_rate ? pct(d.latest.oos_hit_rate, 0) : "—"} />
                    <Stat label="Brier" value={d.latest.oos_brier ?? "—"} />
                  </div>
                  <p className="text-xs text-muted">
                    {d.in_use
                      ? `Contributing at weight ${pct(d.signal_weight, 0)}.`
                      : "Below the promotion gate — signal stays off by design."}
                  </p>
                </div>
              )
            }
          </AsyncBlock>
        </Card>
      </div>
    </div>
  );
}
