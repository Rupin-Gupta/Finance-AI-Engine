import { lazy, Suspense, useState } from "react";
import { Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import { Loading } from "./components/ui";

// Route-level code-splitting — recharts-heavy pages load on demand.
const Overview = lazy(() => import("./pages/Overview"));
const Portfolio = lazy(() => import("./pages/Portfolio"));
const Recommendations = lazy(() => import("./pages/Recommendations"));
const Risk = lazy(() => import("./pages/Risk"));
const Backtesting = lazy(() => import("./pages/Backtesting"));
const Signals = lazy(() => import("./pages/Signals"));
const Reports = lazy(() => import("./pages/Reports"));
const SettingsPage = lazy(() => import("./pages/Settings"));

export default function App() {
  // Selected symbol is shared app-wide (top-bar search drives the analysis pages).
  const [symbol, setSymbol] = useState("AAPL");
  return (
    <AppShell symbol={symbol} setSymbol={setSymbol}>
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/" element={<Overview onPick={setSymbol} />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/recommendations" element={<Recommendations symbol={symbol} />} />
          <Route path="/risk" element={<Risk />} />
          <Route path="/backtesting" element={<Backtesting symbol={symbol} />} />
          <Route path="/signals" element={<Signals />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}
