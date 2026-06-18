import { useCallback } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import type {
  Alert,
  MlModelResponse,
  RegimeResponse,
  WatchlistResponse,
} from "../lib/types";
import { AsyncBlock, Card, Chip, Empty, RecBadge, Stat } from "../components/ui";
import { signedPct, titleCase } from "../lib/format";

const regimeTone = (r?: string | null) =>
  r === "bull" ? "bull" : r === "bear" ? "bear" : r === "high_vol" ? "accent" : "neutral";

export default function Overview({ onPick }: { onPick: (s: string) => void }) {
  const regime = useAsync<RegimeResponse>(useCallback(() => api.get("/v1/regime"), []), true);
  const alerts = useAsync<Alert[]>(useCallback(() => api.get("/v1/alerts"), []), true);
  const watch = useAsync<WatchlistResponse>(useCallback(() => api.get("/v1/watchlist"), []), true);
  const ml = useAsync<MlModelResponse>(useCallback(() => api.get("/v1/ml/model"), []), true);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Overview</h1>
        <p className="text-sm text-muted">Market pulse, live signals, and what needs attention.</p>
      </header>

      {/* Market pulse KPIs */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="US Regime"
          value={regime.data?.us ? titleCase(regime.data.us.regime) : "—"}
          sub={regime.data?.us?.reason}
          tone={regimeTone(regime.data?.us?.regime)}
        />
        <Stat
          label="India Regime"
          value={regime.data?.india ? titleCase(regime.data.india.regime) : "—"}
          sub={regime.data?.india?.reason}
          tone={regimeTone(regime.data?.india?.regime)}
        />
        <Stat
          label="Open Alerts"
          value={alerts.data ? alerts.data.length : "—"}
          sub="anomaly · drift · stops · data"
          tone={alerts.data && alerts.data.length > 0 ? "accent" : "muted"}
        />
        <Stat
          label="ML Model"
          value={ml.data?.in_use ? "Active" : "Off"}
          sub={ml.data?.latest ? `AUC ${ml.data.latest.oos_auc ?? "—"}` : "no model"}
          tone={ml.data?.in_use ? "bull" : "muted"}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* Top signals from watchlist */}
        <Card title="Watchlist Signals" className="lg:col-span-2">
          <AsyncBlock
            state={watch}
            empty={
              <Empty>
                No watchlist yet.{" "}
                <Link to="/portfolio" className="text-info underline">
                  Add holdings
                </Link>
              </Empty>
            }
          >
            {(data) =>
              data.items.length === 0 ? (
                <Empty>
                  Watchlist is empty —{" "}
                  <Link to="/portfolio" className="text-info underline">
                    add a symbol
                  </Link>
                </Empty>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b">
                        <th className="th">Symbol</th>
                        <th className="th">Signal</th>
                        <th className="th text-right">Price</th>
                        <th className="th text-right">P&amp;L</th>
                        <th className="th text-right">Sentiment</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.items.map((it) => (
                        <tr key={it.symbol} className="row-hover border-b last:border-0">
                          <td className="td">
                            <button
                              className="font-mono font-medium text-info hover:underline"
                              onClick={() => onPick(it.symbol)}
                            >
                              {it.symbol}
                            </button>
                          </td>
                          <td className="td">{it.recommendation ? <RecBadge rec={it.recommendation} /> : "—"}</td>
                          <td className="num td text-right">{it.current_price ?? "—"}</td>
                          <td
                            className={`num td text-right ${
                              (it.unrealized_pnl_pct ?? 0) >= 0 ? "text-bull" : "text-bear"
                            }`}
                          >
                            {signedPct(it.unrealized_pnl_pct)}
                          </td>
                          <td className="num td text-right">
                            {it.sentiment_score === null ? "—" : it.sentiment_score.toFixed(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            }
          </AsyncBlock>
        </Card>

        {/* Recent alerts */}
        <Card title="Recent Alerts">
          <AsyncBlock state={alerts} empty={<Empty>No alerts.</Empty>}>
            {(data) =>
              data.length === 0 ? (
                <Empty>Nothing flagged.</Empty>
              ) : (
                <ul className="space-y-2">
                  {data.slice(0, 8).map((a) => (
                    <li key={a.id} className="flex items-center justify-between gap-2 text-sm">
                      <span className="flex items-center gap-2">
                        <Chip tone="accent">{titleCase(a.alert_type)}</Chip>
                        <span className="font-mono text-text">{a.symbol}</span>
                      </span>
                      <time className="text-2xs text-muted" dateTime={a.detected_at}>
                        {a.detected_at.slice(5, 16).replace("T", " ")}
                      </time>
                    </li>
                  ))}
                </ul>
              )
            }
          </AsyncBlock>
        </Card>
      </div>
    </div>
  );
}
