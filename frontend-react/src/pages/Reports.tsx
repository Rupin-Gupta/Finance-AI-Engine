import { useCallback, useState } from "react";
import { api } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import type { ReportRow } from "../lib/types";
import { AsyncBlock, Card, Empty, ErrorState } from "../components/ui";

export default function Reports() {
  const reports = useAsync<ReportRow[]>(
    useCallback(() => api.get("/v1/reports?limit=20&offset=0"), []),
    true,
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function generate() {
    setBusy(true);
    setErr(null);
    try {
      await api.post("/v1/reports/generate");
      await reports.run();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Reports</h1>
          <p className="text-sm text-muted">AI-generated sector summaries.</p>
        </div>
        <button className="btn btn-accent" onClick={generate} disabled={busy}>
          {busy ? "Generating…" : "Generate Reports"}
        </button>
      </header>

      {err && <ErrorState message={err} />}

      <AsyncBlock state={reports} empty={<Empty>No reports yet.</Empty>}>
        {(rows) =>
          rows.length === 0 ? (
            <Empty>No reports yet — generate one.</Empty>
          ) : (
            <div className="space-y-3">
              {rows.map((r, i) => (
                <Card key={i}>
                  <div className="mb-1 flex items-center justify-between">
                    <h3 className="text-sm font-semibold">{r.query}</h3>
                    <time className="text-2xs text-muted" dateTime={r.created_at}>
                      {r.created_at.slice(0, 16).replace("T", " ")}
                    </time>
                  </div>
                  <p className="whitespace-pre-wrap text-sm text-muted">{r.response}</p>
                </Card>
              ))}
            </div>
          )
        }
      </AsyncBlock>
    </div>
  );
}
