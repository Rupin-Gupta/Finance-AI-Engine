import { useCallback, useEffect, useRef, useState } from "react";

interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

/** Run an async fn on demand (or on mount via `immediate`), tracking loading/error.
 *  Ignores results from superseded calls so fast re-runs don't flicker stale data. */
export function useAsync<T>(fn: () => Promise<T>, immediate = false) {
  const [state, setState] = useState<AsyncState<T>>({ data: null, loading: false, error: null });
  const callId = useRef(0);

  const run = useCallback(async () => {
    const id = ++callId.current;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await fn();
      if (id === callId.current) setState({ data, loading: false, error: null });
    } catch (e) {
      if (id === callId.current)
        setState({ data: null, loading: false, error: e instanceof Error ? e.message : String(e) });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fn]);

  useEffect(() => {
    if (immediate) void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [immediate]);

  return { ...state, run };
}
