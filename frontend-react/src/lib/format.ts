export const pct = (v: number | null | undefined, dp = 1): string =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(dp)}%`;

export const signedPct = (v: number | null | undefined, dp = 1): string =>
  v === null || v === undefined ? "—" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(dp)}%`;

export const money = (v: number | null | undefined, dp = 2): string =>
  v === null || v === undefined
    ? "—"
    : v.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp });

export const num = (v: number | null | undefined, dp = 2): string =>
  v === null || v === undefined ? "—" : v.toFixed(dp);

export const titleCase = (s: string): string =>
  s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
