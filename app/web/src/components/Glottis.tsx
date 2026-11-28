// Editors of the glottis workspace: the glottis models (which one VTL uses),
// the static parameters of that model, its shapes (modal, ...), the control
// parameters of the chosen shape, and the glottal waveform of a held vowel.
// The same tables serve every model, the triangular body-cover one included.

import { useLatest } from "../compute";
import type { T } from "../i18n";
import { client, useClient } from "../store";
import { useWorkspace } from "../workspace";
import { useSize } from "./plots";
import { ValueRow } from "./Params";
import { Row, ShapeList, statusItems } from "./Shapes";

/** The four models VTL has, in its order. A speaker file may lack some. */
export const GLOTTIS_MODELS = [
  "Geometric glottis 2025", "Geometric glottis 2019", "Triangular glottis", "Triangular body-cover glottis",
];

const unitTitle = (name: string, unit: string) => (unit ? `${name} [${unit}]` : name);

export function ModelList({ t }: { t: T }) {
  const c = useClient();
  const w = useWorkspace();
  const sp = c.project!.speakers[w.speaker!];
  const selEdited = c.isEdited(w.speaker!, ["glottis_selected"]);
  return (
    <div className="list">
      {GLOTTIS_MODELS.map((m) => {
        const has = sp.glottis.models.some((x) => x.type === m);
        const sel = sp.glottis.selected === m;
        return (
          <Row key={m} t={t} name={m} sel={sel} edited={w.editedModels.has(m) || (sel && selEdited)} disabled={!has}
            title={has ? m : `${m} · ${t("glottis.absent")}`}
            tag={sel ? <span className="mono tag">{t("glottis.in_use")}</span> : undefined}
            level={c.statusOf(w.speaker!, ["glottis_model", m])}
            onSelect={() => { if (!sel) void client.op("glottis.select_model", { speaker: w.speaker, model: m }); }}
            menu={has ? () => statusItems(t, w.speaker!, ["glottis_model", m]) : null} />
        );
      })}
    </div>
  );
}

export function StaticParams() {
  const c = useClient();
  const w = useWorkspace();
  const m = w.glottis!;
  return (
    <div className="params">
      <div className="group">
        {m.static.map((p) => (
          <ValueRow key={p.abbr} wide label={p.abbr} title={unitTitle(p.name, p.unit)} min={p.min} max={p.max}
            value={p.value} edited={c.isEdited(w.speaker!, ["glottis_static", m.type, p.abbr])}
            op="glottis.set_static" args={{ speaker: w.speaker, model: m.type, param: p.abbr }} />
        ))}
      </div>
    </div>
  );
}

export function GShapeList({ t }: { t: T }) {
  const w = useWorkspace();
  return <ShapeList t={t} speaker={w.speaker!} kind="glottis" model={w.glottis!.type} names={w.gshapeNames}
    selected={w.gshape} edited={w.editedGShapes} onSelect={w.setGShape} />;
}

export function GShapeParams() {
  const c = useClient();
  const w = useWorkspace();
  const m = w.glottis!;
  const values = m.shapes[w.gshape!];
  return (
    <div className="params">
      <div className="group">
        {m.control.map((p) => (
          <ValueRow key={p.abbr} wide label={p.abbr} title={unitTitle(p.name, p.unit)} min={p.min} max={p.max}
            value={values[p.index]} edited={c.isEdited(w.speaker!, ["glottis_shape", m.type, w.gshape!, p.index])}
            op="glottis.set_param" args={{ speaker: w.speaker, model: m.type, shape: w.gshape, param: p.abbr }} />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// The glottal waveform

export interface GlottisWave {
  sampling_rate: number; start_s: number; f0_target: number; f0_measured: number | null; pressure: number;
  area_cm2: number[]; flow_cm3_s: number[]; output: number[];
}

/** The waveform of the chosen glottis shape with the vocal tract shape chosen in the
 *  vocal tract workspace; asked again whenever the speaker's values change. */
export function useGlottisWave(): GlottisWave | null {
  const c = useClient();
  const w = useWorkspace();
  const sp = w.speaker ? c.project?.speakers[w.speaker] : undefined;
  const payload = sp && w.glottis && w.gshape && w.shape ? {
    speaker: w.speaker, tract_shape: w.shape, glottis_shape: w.gshape, duration: 0.3,
    // not read by the server: makes the request new when a value it depends on changes
    rev: [w.glottis.type, w.glottis.static.map((p) => p.value), w.glottis.shapes[w.gshape], sp.tract.shapes[w.shape]],
  } : null;
  return useLatest<GlottisWave>("glottis_wave", payload);
}

function f0Text(t: T, wave: GlottisWave) {
  if (wave.f0_measured === null) return t("wave.not_periodic", { target: wave.f0_target.toFixed(0) });
  return t("wave.f0", { f0: wave.f0_measured.toFixed(1), target: wave.f0_target.toFixed(0) });
}

const M = { l: 56, r: 16, t: 4, b: 44 }; // the bottom holds the time axis and a line for F0
const LABEL = 20; // a line above each trace for its name, so the name never sits on the trace

export function WaveView({ wave, t }: { wave: GlottisWave | null; t: T }) {
  const [box, size] = useSize<HTMLDivElement>();
  let body = null;
  if (wave && size.w > 0 && wave.flow_cm3_s.length > 1) {
    const traces: [string, number[], (v: number) => string][] = [
      [t("wave.area"), wave.area_cm2, (v) => v.toFixed(3)],
      [t("wave.flow"), wave.flow_cm3_s, (v) => v.toFixed(0)],
      [t("wave.output"), wave.output, (v) => v.toFixed(3)],
    ];
    const n = wave.flow_cm3_s.length;
    const W = size.w - M.l - M.r;
    const gap = 4;
    const H = (size.h - M.t - M.b - gap * (traces.length - 1)) / traces.length - LABEL;
    const X = (i: number) => M.l + (i / (n - 1)) * W;
    const ms = (n / wave.sampling_rate) * 1000;
    const step = ms > 30 ? 10 : 5;
    const xt = Array.from({ length: Math.floor(ms / step) + 1 }, (_, i) => i * step);
    const period = wave.sampling_rate / wave.f0_target;
    const periods = Array.from({ length: Math.floor((n - 1) / period) + 1 }, (_, k) => k * period);
    body = (
      <>
        {H > 12 && traces.map(([label, ys, fmt], k) => {
          const top = M.t + k * (H + LABEL + gap) + LABEL;
          let lo = Math.min(...ys), hi = Math.max(...ys);
          if (k === 0) lo = Math.min(lo, 0); // area from 0
          if (hi - lo < 1e-12) { hi += 1; lo -= 1; }
          const Y = (v: number) => top + H - ((v - lo) / (hi - lo)) * H;
          const ptsStr = ys.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
          return (
            <g key={k}>
              {/* the target period, within the band only (the name line stays clear) */}
              {periods.map((p) => <line key={p} className="grid" x1={X(p)} x2={X(p)} y1={top} y2={top + H} />)}
              <line className="axis" x1={M.l} x2={M.l} y1={top} y2={top + H} />
              <line className="axis" x1={M.l - 4} x2={M.l} y1={top} y2={top} />
              <line className="axis" x1={M.l - 4} x2={M.l} y1={top + H} y2={top + H} />
              {/* tick values left of the axis, inside the band (the top one hangs below its tick) */}
              <text x={M.l - 8} y={top + 9} textAnchor="end">{fmt(hi)}</text>
              {H > 28 && <text x={M.l - 8} y={top + H} textAnchor="end">{fmt(lo)}</text>}
              <polyline className="line" points={ptsStr} />
              <text className="peaklab" x={M.l} y={top - 6}>{label}</text>
            </g>
          );
        })}
        <line className="axis" x1={M.l} x2={M.l + W} y1={size.h - M.b} y2={size.h - M.b} />
        {xt.map((v) => (
          <text key={v} x={M.l + (v / ms) * W} y={size.h - M.b + 16} textAnchor="middle">{v}</text>
        ))}
        <text x={M.l + W} y={size.h - 8} textAnchor="end">{t("wave.ms")}</text>
        <text className="peaklab" x={M.l} y={size.h - 8}>{f0Text(t, wave)}</text>
      </>
    );
  }
  return (
    <div className="abody" ref={box}>
      <svg className="fill plot" width={size.w} height={size.h}>{body}</svg>
      {!wave && <div className="empty overlay">{t("wave.computing")}</div>}
    </div>
  );
}
