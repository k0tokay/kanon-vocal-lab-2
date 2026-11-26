import { useLayoutEffect, useRef, useState } from "react";
import type { Computed } from "../compute";
import type { T } from "../i18n";

/** Pixel size of an element, kept up to date. */
export function useSize<E extends HTMLElement>() {
  const ref = useRef<E>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, size] as const;
}

const pts = (a: [number, number][]) => a.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");

// ---------------------------------------------------------------------------
// Midsagittal outline

const WALLS = ["upper_cover_back", "uvula", "upper_front", "lower_cover_larynx", "epiglottis", "lower_front"];
const TEETH = ["upper_teeth_inner", "upper_teeth_outer", "upper_teeth_back",
  "lower_teeth_inner", "lower_teeth_outer", "lower_teeth_back"];

type Box = { x0: number; x1: number; y0: number; y1: number };

function bounds(c: Record<string, [number, number][]>): Box {
  const b = { x0: Infinity, x1: -Infinity, y0: Infinity, y1: -Infinity };
  for (const line of Object.values(c))
    for (const [x, y] of line) {
      b.x0 = Math.min(b.x0, x); b.x1 = Math.max(b.x1, x);
      b.y0 = Math.min(b.y0, y); b.y1 = Math.max(b.y1, y);
    }
  return b;
}

export function TractView({ speaker, cur, saved, t }: {
  speaker: string; cur: Computed | null; saved: Computed | null; t: T;
}) {
  const [box, size] = useSize<HTMLDivElement>();
  // A stable frame per speaker: it only grows, so the drawing does not jump while dragging.
  const frames = useRef(new Map<string, Box>());
  let frame = frames.current.get(speaker);
  if (cur?.contours) {
    const b = bounds(cur.contours);
    frame = frame
      ? { x0: Math.min(frame.x0, b.x0), x1: Math.max(frame.x1, b.x1), y0: Math.min(frame.y0, b.y0), y1: Math.max(frame.y1, b.y1) }
      : b;
    frames.current.set(speaker, frame);
  }
  const pad = 24;
  let body = null;
  if (frame && cur?.contours && size.w > 0) {
    const s = Math.max(1, Math.min((size.w - 2 * pad) / (frame.x1 - frame.x0), (size.h - 2 * pad - 24) / (frame.y1 - frame.y0)));
    const ox = (size.w - s * (frame.x1 - frame.x0)) / 2 - s * frame.x0;
    const oy = (size.h - 24 - s * (frame.y1 - frame.y0)) / 2 + s * frame.y1;
    const px = (line: [number, number][]) => line.map(([x, y]) => [ox + s * x, oy - s * y] as [number, number]);
    const c = cur.contours;
    body = (
      <>
        {saved?.contours && [...WALLS, "tongue"].map((n) =>
          <polyline key={"r" + n} className="ref" points={pts(px(saved.contours![n]))} />)}
        <polygon className="tongue" points={pts(px(c.tongue))} />
        <polyline className="side" points={pts(px(c.tongue_side))} />
        {TEETH.map((n) => <polyline key={n} className="teeth" points={pts(px(c[n]))} />)}
        {WALLS.map((n) => <polyline key={n} className="wall" points={pts(px(c[n]))} />)}
        <text className="lab" x={16} y={size.h - 12}>
          {t("tract.scale", { px: s.toFixed(0) })}{saved?.contours ? " · " + t("tract.legend.saved") : ""}
        </text>
      </>
    );
  }
  return (
    <div className="abody" ref={box}>
      <svg className="fill tract" width={size.w} height={size.h}>{body}</svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Plots with axes

const M = { l: 40, r: 16, t: 12, b: 28 };

function niceCeil(v: number, step: number) { return Math.max(step, Math.ceil(v / step) * step); }

export function AreaPlot({ cur, saved, t }: { cur: Computed | null; saved: Computed | null; t: T }) {
  const [box, size] = useSize<HTMLDivElement>();
  const tubes = [cur?.tube, saved?.tube].filter(Boolean) as NonNullable<Computed["tube"]>[];
  let body = null;
  if (cur?.tube && size.w > 0) {
    const end = (tb: NonNullable<Computed["tube"]>) => tb.position_cm[tb.position_cm.length - 1] + tb.length_cm[tb.length_cm.length - 1];
    const xmax = niceCeil(Math.max(...tubes.map(end)), 2);
    const ymax = niceCeil(Math.max(...tubes.flatMap((tb) => tb.area_cm2)), 2);
    const W = size.w - M.l - M.r, H = size.h - M.t - M.b;
    const X = (x: number) => M.l + (x / xmax) * W;
    const Y = (y: number) => M.t + H - (y / ymax) * H;
    const steps = (tb: NonNullable<Computed["tube"]>) => {
      const p: [number, number][] = [];
      tb.area_cm2.forEach((a, i) => { p.push([X(tb.position_cm[i]), Y(a)], [X(tb.position_cm[i] + tb.length_cm[i]), Y(a)]); });
      return pts(p);
    };
    const ystep = ymax > 8 ? 4 : 2;
    const yt = Array.from({ length: ymax / ystep + 1 }, (_, i) => i * ystep);
    const xt = Array.from({ length: xmax / 4 + 1 }, (_, i) => i * 4);
    body = (
      <>
        {yt.slice(1).map((v) => <line key={v} className="grid" x1={M.l} x2={M.l + W} y1={Y(v)} y2={Y(v)} />)}
        {yt.map((v) => <text key={"y" + v} x={M.l - 8} y={Y(v) + 4} textAnchor="end">{v}</text>)}
        {xt.map((v) => <text key={"x" + v} x={X(v)} y={M.t + H + 16} textAnchor="middle">{v}</text>)}
        <line className="axis" x1={M.l} x2={M.l + W} y1={Y(0)} y2={Y(0)} />
        <line className="axis" x1={M.l} x2={M.l} y1={M.t} y2={Y(0)} />
        {saved?.tube && <polyline className="ref" points={steps(saved.tube)} />}
        <polyline className="line" points={steps(cur.tube)} />
      </>
    );
  }
  return (
    <div className="abody" ref={box} title={t("ax.distance")}>
      <svg className="fill plot" width={size.w} height={size.h}>{body}</svg>
    </div>
  );
}

const db = (m: number) => 20 * Math.log10(Math.max(m, 1e-9));

export function SpectrumPlot({ cur, saved, fmax }: { cur: Computed | null; saved: Computed | null; fmax: number }) {
  const [box, size] = useSize<HTMLDivElement>();
  let body = null;
  if (cur?.spectrum && size.w > 0) {
    const specs = [cur.spectrum, saved?.spectrum].filter(Boolean) as NonNullable<Computed["spectrum"]>[];
    const top = niceCeil(Math.max(...specs.flatMap((s) => s.magnitude.map(db))), 10);
    const bottom = top - 60;
    const W = size.w - M.l - M.r, H = size.h - M.t - M.b;
    const X = (f: number) => M.l + (f / fmax) * W;
    const Y = (d: number) => M.t + H - ((Math.max(d, bottom) - bottom) / (top - bottom)) * H;
    const line = (s: NonNullable<Computed["spectrum"]>) => pts(s.freq.map((f, i) => [X(f), Y(db(s.magnitude[i]))]));
    const yt = [bottom, bottom + 20, bottom + 40, top];
    const xt = Array.from({ length: Math.floor(fmax / 1000) + 1 }, (_, i) => i * 1000);
    const peaks = (cur.formants ?? []).slice(0, 3);
    body = (
      <>
        {yt.slice(1).map((v) => <line key={v} className="grid" x1={M.l} x2={M.l + W} y1={Y(v)} y2={Y(v)} />)}
        {yt.map((v) => <text key={"y" + v} x={M.l - 8} y={Y(v) + 4} textAnchor="end">{v}</text>)}
        {xt.map((v) => <text key={"x" + v} x={X(v)} y={M.t + H + 16} textAnchor="middle">{v / 1000}k</text>)}
        <line className="axis" x1={M.l} x2={M.l + W} y1={Y(bottom)} y2={Y(bottom)} />
        <line className="axis" x1={M.l} x2={M.l} y1={M.t} y2={Y(bottom)} />
        {peaks.map((f, i) => (
          <g key={i}>
            <line className="peak" x1={X(f)} x2={X(f)} y1={M.t} y2={Y(bottom)} />
            {/* a label that would run into the previous one goes one line lower */}
            <text className="peaklab" x={X(f) + 4}
              y={M.t + 12 + (i > 0 && X(f) - X(peaks[i - 1]) < 24 ? 20 : 0)}>F{i + 1}</text>
          </g>
        ))}
        {saved?.spectrum && <polyline className="ref" points={line(saved.spectrum)} />}
        <polyline className="line" points={line(cur.spectrum)} />
      </>
    );
  }
  return (
    <div className="abody" ref={box}>
      <svg className="fill plot" width={size.w} height={size.h}>{body}</svg>
    </div>
  );
}
