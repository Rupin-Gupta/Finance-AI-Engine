import { useCallback, useState } from "react";
import { api } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import type { WatchlistResponse } from "../lib/types";

const del = api.del;
import { AsyncBlock, Card, Empty, ErrorState, RecBadge, Stat } from "../components/ui";
import { money, pct, signedPct } from "../lib/format";

export default function Portfolio() {
  const watch = useAsync<WatchlistResponse>(useCallback(() => api.get("/v1/watchlist"), []), true);

  const [sym, setSym] = useState("");
  const [qty, setQty] = useState("");
  const [cost, setCost] = useState("");
  const [addErr, setAddErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setAddErr(null);
    setBusy(true);
    try {
      await api.post("/v1/watchlist", {
        symbol: sym.trim().toUpperCase(),
        quantity: qty ? Number(qty) : null,
        cost_basis: cost ? Number(cost) : null,
      });
      setSym("");
      setQty("");
      setCost("");
      await watch.run();
    } catch (e) {
      setAddErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove(symbol: string) {
    try {
      await del(`/v1/watchlist/${encodeURIComponent(symbol)}`);
      await watch.run();
    } catch (e) {
      setAddErr(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Portfolio Analysis</h1>
        <p className="text-sm text-muted">Holdings with live price, unrealized P&amp;L, and suggested size.</p>
      </header>

      <AsyncBlock state={watch}>
        {(d) => (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat label="Positions" value={d.totals.positions} />
              <Stat label="Market Value" value={money(d.totals.market_value)} />
              <Stat label="Cost Basis" value={money(d.totals.cost_value)} />
              <Stat
                label="Unrealized P&L"
                value={money(d.totals.unrealized_pnl)}
                sub={signedPct(d.totals.unrealized_pnl_pct)}
                tone={(d.totals.unrealized_pnl ?? 0) >= 0 ? "bull" : "bear"}
              />
            </div>

            <Card title="Holdings">
              {d.items.length === 0 ? (
                <Empty>No holdings yet — add one below.</Empty>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b">
                        <th className="th">Symbol</th>
                        <th className="th">Signal</th>
                        <th className="th text-right">Qty</th>
                        <th className="th text-right">Cost</th>
                        <th className="th text-right">Price</th>
                        <th className="th text-right">P&amp;L</th>
                        <th className="th text-right">Sugg. size</th>
                        <th className="th"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.items.map((it) => (
                        <tr key={it.symbol} className="row-hover border-b last:border-0">
                          <td className="num td font-medium">{it.symbol}</td>
                          <td className="td">{it.recommendation ? <RecBadge rec={it.recommendation} /> : "—"}</td>
                          <td className="num td text-right">{it.quantity ?? "—"}</td>
                          <td className="num td text-right">{it.cost_basis ?? "—"}</td>
                          <td className="num td text-right">{it.current_price ?? "—"}</td>
                          <td
                            className={`num td text-right ${
                              (it.unrealized_pnl ?? 0) >= 0 ? "text-bull" : "text-bear"
                            }`}
                          >
                            {it.unrealized_pnl === null ? "—" : money(it.unrealized_pnl)}{" "}
                            <span className="text-2xs text-muted">{signedPct(it.unrealized_pnl_pct)}</span>
                          </td>
                          <td className="num td text-right">{pct(it.suggested_position_pct)}</td>
                          <td className="td text-right">
                            <button
                              className="text-2xs text-muted hover:text-bear"
                              aria-label={`Remove ${it.symbol}`}
                              onClick={() => remove(it.symbol)}
                            >
                              Remove
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </>
        )}
      </AsyncBlock>

      <Card title="Add Holding">
        <form onSubmit={add} className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="add-sym" className="text-2xs uppercase tracking-wide text-muted">
              Symbol
            </label>
            <input id="add-sym" className="input w-32" value={sym} onChange={(e) => setSym(e.target.value)} required />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="add-qty" className="text-2xs uppercase tracking-wide text-muted">
              Quantity
            </label>
            <input id="add-qty" className="input w-28" inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="add-cost" className="text-2xs uppercase tracking-wide text-muted">
              Cost basis
            </label>
            <input id="add-cost" className="input w-28" inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} />
          </div>
          <button type="submit" className="btn btn-accent" disabled={busy}>
            {busy ? "Adding…" : "Add"}
          </button>
        </form>
        {addErr && (
          <div className="mt-3">
            <ErrorState message={addErr} />
          </div>
        )}
      </Card>
    </div>
  );
}
