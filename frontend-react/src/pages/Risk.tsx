import { useState } from "react";
import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { api } from "../lib/api";
import type { RiskReport, StopsResponse } from "../lib/types";
import { AsyncBlock, Card, Chip, Empty, Stat } from "../components/ui";
import { useAsync } from "../lib/useAsync";
import { money, pct, signedPct, titleCase } from "../lib/format";

const DONUT = ["#F5B301", "#5AA2F0", "#22C55E", "#F0556B", "#C9A227", "#9AA7B8", "#8B5CF6"];

const riskTone = (lvl?: string) =>
  lvl === "Low" ? "bull" : lvl === "Extreme" || lvl === "High" ? "bear" : "accent";

export default function Risk() {
  const [source, setSource] = useState<"watchlist" | "paper">("watchlist");

  const risk = useAsync<RiskReport>(() => api.get(`/v1/portfolio/risk${api.qs({ source })}`));
  const stops = useAsync<StopsResponse>(() => api.get(`/v1/portfolio/stops${api.qs({ source })}`));

  function analyze() {
    void risk.run();
    void stops.run();
  }

  // Paper-trade ticket — fills the empty paper book so it has something to assess.
  const [tSym, setTSym] = useState("");
  const [tSide, setTSide] = useState<"BUY" | "SELL">("BUY");
  const [tQty, setTQty] = useState("");
  const [tBusy, setTBusy] = useState(false);
  const [tErr, setTErr] = useState<string | null>(null);
  const [tOk, setTOk] = useState<string | null>(null);

  async function placeTrade(e: React.FormEvent) {
    e.preventDefault();
    setTErr(null);
    setTOk(null);
    setTBusy(true);
    try {
      const r = await api.post<{ trade: { side: string; quantity: number; price: number }; cash: number }>(
        "/v1/paper/trade",
        { symbol: tSym.trim().toUpperCase(), side: tSide, quantity: Number(tQty) },
      );
      setTOk(`${r.trade.side} ${r.trade.quantity} ${tSym.trim().toUpperCase()} @ ${r.trade.price.toFixed(2)}`);
      setTQty("");
      if (source === "paper") analyze(); // refresh the report against the new position
    } catch (err) {
      setTErr(err instanceof Error ? err.message : String(err));
    } finally {
      setTBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Risk Analysis</h1>
          <p className="text-sm text-muted">
            Concentration, correlation, historical VaR/CVaR, and stop-loss exposure.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <fieldset className="flex items-center gap-1 rounded-md border p-1" aria-label="Holdings source">
            {(["watchlist", "paper"] as const).map((s) => (
              <button
                key={s}
                className={`btn min-h-[32px] border-0 px-2 text-xs ${
                  source === s ? "btn-accent" : "text-muted"
                }`}
                aria-pressed={source === s}
                onClick={() => setSource(s)}
              >
                {s}
              </button>
            ))}
          </fieldset>
          <button className="btn btn-accent" onClick={analyze} disabled={risk.loading}>
            {risk.loading ? "Assessing…" : "Analyze"}
          </button>
        </div>
      </header>

      {source === "paper" && (
        <Card title="Place Paper Trade">
          <form onSubmit={placeTrade} className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <label htmlFor="t-sym" className="text-2xs uppercase tracking-wide text-muted">Symbol</label>
              <input id="t-sym" className="input w-32" value={tSym} onChange={(e) => setTSym(e.target.value)} required />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="t-side" className="text-2xs uppercase tracking-wide text-muted">Side</label>
              <select id="t-side" className="input w-24" value={tSide} onChange={(e) => setTSide(e.target.value as "BUY" | "SELL")}>
                <option value="BUY">BUY</option>
                <option value="SELL">SELL</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="t-qty" className="text-2xs uppercase tracking-wide text-muted">Quantity</label>
              <input id="t-qty" className="input w-28" inputMode="decimal" value={tQty} onChange={(e) => setTQty(e.target.value)} required />
            </div>
            <button type="submit" className="btn btn-accent" disabled={tBusy}>
              {tBusy ? "Placing…" : "Place trade"}
            </button>
          </form>
          <p className="mt-2 text-2xs text-muted">Fills at the latest stored price. SELL cannot exceed held quantity (no shorting).</p>
          {tOk && <div className="mt-3 rounded-md border border-bull/40 bg-bull/10 p-2 text-sm text-bull">✓ {tOk}</div>}
          {tErr && <div className="mt-3 rounded-md border border-bear/40 bg-bear/10 p-2 text-sm text-bear">{tErr}</div>}
        </Card>
      )}

      <AsyncBlock state={risk} empty={<Empty>Pick a source and click Analyze.</Empty>}>
        {(d) =>
          d.positions === 0 ? (
            <Empty>No {source} positions with value to assess.</Empty>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Stat
                  label="Risk Score"
                  value={`${d.risk_score?.score ?? "—"}/100`}
                  sub={d.risk_score?.level}
                  tone={riskTone(d.risk_score?.level)}
                />
                <Stat
                  label={`VaR ${d.var ? pct(d.var.confidence, 0) : ""}`}
                  value={d.var ? pct(d.var.var_pct, 2) : "—"}
                  sub={d.var ? `≈ ${money(d.var.var_value)}` : "1-day"}
                  tone="bear"
                />
                <Stat
                  label="CVaR (tail)"
                  value={d.var ? pct(d.var.cvar_pct, 2) : "—"}
                  sub={d.var ? `≈ ${money(d.var.cvar_value)}` : "1-day"}
                  tone="bear"
                />
                <Stat
                  label="Avg Correlation"
                  value={d.correlation ? d.correlation.avg_pairwise.toFixed(2) : "—"}
                  sub="pairwise"
                />
              </div>

              {d.warnings && d.warnings.length > 0 && (
                <Card title="Warnings">
                  <ul className="space-y-1">
                    {d.warnings.map((w, i) => (
                      <li key={i} className="flex items-center gap-2 text-sm text-accent">
                        ⚠ {w}
                      </li>
                    ))}
                  </ul>
                </Card>
              )}

              <div className="grid gap-4 lg:grid-cols-2">
                <Card title="Sector Exposure">
                  {d.sector_exposure ? (
                    <div className="flex items-center gap-4">
                      <ResponsiveContainer width="55%" height={220}>
                        <PieChart>
                          <Pie
                            data={Object.entries(d.sector_exposure.by_sector).map(([name, value]) => ({
                              name,
                              value,
                            }))}
                            dataKey="value"
                            nameKey="name"
                            innerRadius={45}
                            outerRadius={85}
                            stroke="#0B0E13"
                          >
                            {Object.keys(d.sector_exposure.by_sector).map((_, i) => (
                              <Cell key={i} fill={DONUT[i % DONUT.length]} />
                            ))}
                          </Pie>
                          <Tooltip
                            formatter={(v: number) => pct(v)}
                            contentStyle={{ background: "#121722", border: "1px solid #232C3B" }}
                          />
                        </PieChart>
                      </ResponsiveContainer>
                      <ul className="flex-1 space-y-1 text-sm">
                        {Object.entries(d.sector_exposure.by_sector).map(([s, v], i) => (
                          <li key={s} className="flex items-center justify-between gap-2">
                            <span className="flex items-center gap-2">
                              <span
                                className="h-2.5 w-2.5 rounded-sm"
                                style={{ background: DONUT[i % DONUT.length] }}
                                aria-hidden
                              />
                              {s}
                            </span>
                            <span className="num text-muted">{pct(v)}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <Empty>No sector data.</Empty>
                  )}
                </Card>

                <Card title="Exposure Breakdown">
                  <div className="space-y-3 text-sm">
                    <div>
                      <div className="mb-1 text-2xs uppercase tracking-wide text-muted">Country</div>
                      {Object.entries(d.country_exposure ?? {}).map(([k, v]) => (
                        <div key={k} className="flex justify-between">
                          <span>{k}</span>
                          <span className="num text-muted">{pct(v)}</span>
                        </div>
                      ))}
                    </div>
                    <div>
                      <div className="mb-1 text-2xs uppercase tracking-wide text-muted">Market cap</div>
                      {Object.entries(d.market_cap_exposure ?? {}).map(([k, v]) => (
                        <div key={k} className="flex justify-between">
                          <span>{titleCase(k)}</span>
                          <span className="num text-muted">{pct(v)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </Card>
              </div>

              {/* Stop-loss monitor */}
              <Card title="Stop-Loss Monitor">
                <AsyncBlock state={stops} empty={<Empty>Click Analyze to evaluate stops.</Empty>}>
                  {(s) =>
                    s.positions.length === 0 ? (
                      <Empty>{s.warnings?.[0] ?? "No positions to monitor."}</Empty>
                    ) : (
                      <>
                        {s.breached_count > 0 ? (
                          <div className="mb-3 rounded-md border border-bear/40 bg-bear/10 p-2 text-sm text-bear">
                            🛑 {s.breached_count} breached: {s.breached.join(", ")}
                          </div>
                        ) : (
                          <div className="mb-3 rounded-md border border-bull/40 bg-bull/10 p-2 text-sm text-bull">
                            ✓ No stops breached.
                          </div>
                        )}
                        <div className="overflow-x-auto">
                          <table className="w-full">
                            <thead>
                              <tr className="border-b">
                                <th className="th">Symbol</th>
                                <th className="th text-right">Current</th>
                                <th className="th text-right">Stop</th>
                                <th className="th text-right">Stop %</th>
                                <th className="th text-right">Dist</th>
                                <th className="th">Type</th>
                                <th className="th"></th>
                              </tr>
                            </thead>
                            <tbody>
                              {s.positions.map((p) => (
                                <tr key={p.symbol} className="row-hover border-b last:border-0">
                                  <td className="num td font-medium">{p.symbol}</td>
                                  <td className="num td text-right">{p.current.toFixed(2)}</td>
                                  <td className="num td text-right">{p.stop_level.toFixed(2)}</td>
                                  <td className="num td text-right">{pct(p.stop_pct)}</td>
                                  <td
                                    className={`num td text-right ${
                                      (p.distance_pct ?? 0) < 0 ? "text-bear" : "text-muted"
                                    }`}
                                  >
                                    {signedPct(p.distance_pct)}
                                  </td>
                                  <td className="td">
                                    <Chip>{p.trailing ? "trailing" : "fixed"}</Chip>
                                  </td>
                                  <td className="td">{p.breached ? "🛑" : "✓"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </>
                    )
                  }
                </AsyncBlock>
              </Card>
            </div>
          )
        }
      </AsyncBlock>
    </div>
  );
}
