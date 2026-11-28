// Results computed by VTL on the server for a parameter vector. At most one
// request per hook is in flight; while it runs, newer inputs replace each
// other and only the latest is sent next, so dragging never queues up work.

import { useEffect, useRef, useState } from "react";
import { client } from "./store";

export interface Tube { length_cm: number[]; area_cm2: number[]; position_cm: number[] }
export interface Computed {
  tube?: Tube;
  formants?: number[];
  spectrum?: { freq: number[]; magnitude: number[] };
  contours?: Record<string, [number, number][]>;
}

export function useComputed(speaker: string | null, params: number[] | null, what: string[], fmax = 5000) {
  return useLatest<Computed>("compute", speaker && params ? { speaker, params, what, fmax, n: 2048 } : null);
}

/** The answer to the latest `payload` for a request `kind`, computed on the server.
 *  A new payload (by value) asks again; null clears the result. */
export function useLatest<R>(kind: string, payload: Record<string, unknown> | null): R | null {
  const [result, setResult] = useState<R | null>(null);
  const inputKey = payload ? JSON.stringify(payload) : null;
  const st = useRef({ running: false, latest: null as string | null, alive: true });

  useEffect(() => {
    st.current.alive = true;
    return () => { st.current.alive = false; };
  }, []);

  useEffect(() => {
    const s = st.current;
    s.latest = inputKey;
    if (!inputKey) { setResult(null); return; }
    if (s.running) return;
    const run = async () => {
      s.running = true;
      while (s.alive && s.latest) {
        const k = s.latest;
        try {
          const r = await client.request<R>(kind, JSON.parse(k));
          // a late answer must not bring back a result after the input went away
          if (s.alive && s.latest !== null) setResult(r);
        } catch { /* reconnecting; the next change retries */ }
        if (s.latest === k) break;
      }
      s.running = false;
    };
    void run();
  }, [inputKey]); // eslint-disable-line react-hooks/exhaustive-deps

  return result;
}
