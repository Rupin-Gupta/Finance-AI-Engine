import { useState } from "react";
import { api, getApiBase, getApiKey, setApiConfig } from "../lib/api";
import { Card, Chip, ErrorState } from "../components/ui";

export default function SettingsPage() {
  const [base, setBase] = useState(getApiBase());
  const [key, setKey] = useState(getApiKey());
  const [saved, setSaved] = useState(false);
  const [test, setTest] = useState<"idle" | "ok" | "fail">("idle");
  const [testMsg, setTestMsg] = useState<string | null>(null);

  function save() {
    setApiConfig(base, key);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }

  async function testConn() {
    setApiConfig(base, key);
    setTest("idle");
    setTestMsg(null);
    try {
      await api.get("/ready");
      // auth-gated probe
      await api.get("/v1/jobs?limit=1");
      setTest("ok");
    } catch (e) {
      setTest("fail");
      setTestMsg(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-sm text-muted">Connect the console to your Finance AI Engine API.</p>
      </header>

      <Card title="API Connection">
        <div className="space-y-4">
          <div className="flex flex-col gap-1">
            <label htmlFor="api-base" className="text-2xs uppercase tracking-wide text-muted">
              API base URL
            </label>
            <input
              id="api-base"
              className="input"
              placeholder="(blank = same origin / dev proxy)"
              value={base}
              onChange={(e) => setBase(e.target.value)}
              spellCheck={false}
            />
            <span className="text-2xs text-muted">
              e.g. <span className="num">http://localhost:8000</span>. Leave blank to use the dev proxy.
            </span>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="api-key" className="text-2xs uppercase tracking-wide text-muted">
              API key
            </label>
            <input
              id="api-key"
              type="password"
              className="input"
              placeholder="X-API-Key"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              spellCheck={false}
              autoComplete="off"
            />
            <span className="text-2xs text-muted">Stored in this browser only (localStorage).</span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button className="btn btn-accent" onClick={save}>
              {saved ? "Saved ✓" : "Save"}
            </button>
            <button className="btn" onClick={testConn}>
              Test connection
            </button>
            {test === "ok" && <Chip tone="bull">Connected</Chip>}
            {test === "fail" && <Chip tone="bear">Failed</Chip>}
          </div>
          {test === "fail" && testMsg && <ErrorState message={testMsg} />}
        </div>
      </Card>

      <Card title="About">
        <p className="text-sm text-muted">
          After-Hours Terminal console for the AI Financial Decision Engine. Talks only to the
          FastAPI <span className="num">/v1/*</span> surface — no direct database access. All numbers
          are tabular monospace by design.
        </p>
      </Card>
    </div>
  );
}
