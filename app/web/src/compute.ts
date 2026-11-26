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
  const [result, setResult] = useState<Computed | null>(null);
  const inputKey = speaker && params ? JSON.stringify([speaker, params]) : null;
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
        const [sp, p] = JSON.parse(k);
        try {
          const r = await client.request<Computed>("compute", { speaker: sp, params: p, what, fmax, n: 2048 });
          if (s.alive) setResult(r);
        } catch { /* reconnecting; the next change retries */ }
        if (s.latest === k) break;
      }
      s.running = false;
    };
    void run();
  }, [inputKey]); // eslint-disable-line react-hooks/exhaustive-deps

  return result;
}
