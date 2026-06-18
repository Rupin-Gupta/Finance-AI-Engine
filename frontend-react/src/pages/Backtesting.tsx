import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../lib/api";
import type { Backtest } from "../lib/types";
import { Card, ErrorState, Loading, Stat } from "../components/ui";
import { num, pct, signedPct } from "../lib/format";

export default function Backtesting({ symbol }: { symbol: string }) {
  const [sym, setSym] = useState(symbol);
  const [days, setDays] = useState(365);
  const [data, setData] = useState<Backtest | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setData(null);
    try {
      setData(
        await api.get<Backtest>(
          `/v1/decision/backtest/${encodeURIComponent(sym.trim().toUpperCase())}${api.qs({ days })}`,
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Backtesting</h1>
        <p className="text-sm text-muted">
          Cost-realistic replay — next-bar-open fills, market-aware costs. Net is the headline.
        </p>
      </header>

      <Card>
        <form onSubmit={run} className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col gap-1">
            <label htmlFor="bt-sym" className="text-2xs uppercase tracking-wide text-muted">
              Symbol
            </label>
            <input id="bt-sym" className="input w-32" value={sym} onChange={(e) => setSym(e.target.value)} required />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="bt-days" className="text-2xs uppercase tracking-wide text-muted">
              Window: <span className="num text-text">{days}d</span>
            </label>
            <input
              id="bt-days"
              type="range"
              min={30}
              max={730}
              step={30}
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="w-56 accent-[color:var(--accent)]"
            />
          </div>
          <button type="submit" className="btn btn-accent" disabled={loading}>
            {loading ? "Replaying…" : "Run Backtest"}
          </button>
        </form>
      </Card>

      {loading && <Loading label="Replaying signals…" />}
      {error && <ErrorState message={error} />}

      {data &&
        (() => {
          // Daily mode → total_return / cumulative; discrete (capital) mode → net_return / equity.
          const net = data.net_return ?? data.total_return;
          const curve = (data.equity_curve ?? []).map((p) => ({
            date: p.date,
            equity: p.equity ?? p.cumulative ?? 0,
          }));
          return (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Stat
                  label="Net Return"
                  value={signedPct(net)}
                  sub={`gross ${signedPct(data.gross_return)}`}
                  tone={(net ?? 0) >= 0 ? "bull" : "bear"}
                />
                <Stat label="Cost Drag" value={pct(data.cost_drag)} tone="muted" />
                <Stat label="Sharpe" value={num(data.sharpe_ratio)} />
                <Stat
                  label="Max Drawdown"
                  value={pct(data.max_drawdown)}
                  sub={`${data.trades ?? 0} trades · win ${pct(data.win_rate)}`}
                  tone="bear"
                />
              </div>

              {curve.length > 1 && (
                <Card title="Equity Curve (net of costs)">
                  <ResponsiveContainer width="100%" height={260}>
                    <LineChart data={curve} margin={{ left: 0, right: 8, top: 8 }}>
                      <CartesianGrid stroke="#232C3B" strokeDasharray="3 3" />
                      <XAxis dataKey="date" tick={{ fill: "#9AA7B8", fontSize: 11 }} minTickGap={48} />
                      <YAxis tick={{ fill: "#9AA7B8", fontSize: 11 }} width={56} domain={["auto", "auto"]} />
                      <Tooltip contentStyle={{ background: "#121722", border: "1px solid #232C3B" }} />
                      <Line type="monotone" dataKey="equity" stroke="#F5B301" dot={false} strokeWidth={2} />
                    </LineChart>
                  </ResponsiveContainer>
                </Card>
              )}

              {data.assumptions && data.assumptions.length > 0 && (
                <Card title="Assumptions">
                  <ul className="list-inside list-disc space-y-1 text-sm text-muted">
                    {data.assumptions.map((a, i) => (
                      <li key={i}>{a}</li>
                    ))}
                  </ul>
                </Card>
              )}
            </div>
          );
        })()}
    </div>
  );
}
