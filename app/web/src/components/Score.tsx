// Editors of the articulation workspace: the gestural score on a time line
// (one lane per VTL gesture sequence, the synthesized sound above them), the
// chosen gesture's values, and the vocal tract at the playhead.
//
// Every edit is an operation on the server (gesture.*), so it can be undone;
// dragging a boundary is one undo step. The playhead, range and selection are
// view state (articulation.ts).

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useLatest, useLatestFresh, type Computed } from "../compute";
import type { T } from "../i18n";
import { LINE_LANES, ZOOM, HEIGHT, articulation, useArticulation } from "../articulation";
import { usePlayer } from "../player";
import { client, useClient, type Gesture, type Score, type SequenceInfo } from "../store";
import { useWorkspace } from "../workspace";
import { ValueRow } from "./Params";
import { AreaPlot, TractView } from "./plots";

const LAB_W = 128; // the lane names
const RULER_H = 24;
const LANE_H = 28; // a lane of blocks: one line
const FOLD_H = 12;
const BLOCK_H = 22; // the blocks of a line lane, at its bottom
const OVERVIEW_H = 24;

// ---------------------------------------------------------------------------
// Data

export function useScore(): { id: string; score: Score } | null {
  const c = useClient();
  const ids = Object.keys(c.project?.scores ?? {});
  return ids.length ? { id: ids[0], score: c.project!.scores[ids[0]] } : null;
}

const starts = (gs: Gesture[]) => { let t = 0; return gs.map((g) => { const s = t; t += g[2]; return s; }); };

export interface SoundView {
  key: string; duration: number; sampling_rate: number;
  envelope: { data: string; count: number; step: number };
  spectrogram: { data: string; frames: number; bands: number; step: number; start: number; fmax: number };
}

function decode<A>(b64: string, Type: new (b: ArrayBuffer) => A): A {
  const s = atob(b64), u = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i);
  return new Type(u.buffer);
}
const decoded = new WeakMap<SoundView, { env: Int8Array; spec: Uint8Array }>();
function arrays(v: SoundView) {
  let d = decoded.get(v);
  if (!d) decoded.set(v, d = { env: decode(v.envelope.data, Int8Array), spec: decode(v.spectrogram.data, Uint8Array) });
  return d;
}

/** What a request about the score depends on: the score and the speaker as they are now. */
function useDeps() {
  const c = useClient();
  const w = useWorkspace();
  const s = useScore();
  if (!s || !w.speaker) return null;
  return { score: s.id, speaker: w.speaker, rev: c.version };
}

/** The score synthesized (synthesized again after every edit, by the server, one at a time). */
export function useScoreSound(): [SoundView | null, boolean] {
  return useLatestFresh<SoundView>("score_sound", useDeps());
}

interface Curves { rate: number; count: number; f0?: number[]; pressure?: number[] }
function useScoreCurves() { return useLatest<Curves>("score_curves", useDeps()); }

/** The vocal tract at the playhead. */
export function useTractAtPlayhead(): Computed | null {
  const a = useArticulation();
  const d = useDeps();
  return useLatest<Computed>("score_tract", d ? { ...d, time: Math.round(a.shared.time * 1000) / 1000 } : null);
}

// ---------------------------------------------------------------------------
// Values as text

function info(score: Score, type: string): SequenceInfo {
  return score.info.find((i) => i.type === type)!;
}

export function gestureLabel(type: string, g: Gesture): string {
  if (type === "velic-gestures") return (+g[0]).toFixed(2);
  if (type === "f0-gestures") return (+g[0]).toFixed(1);
  if (type === "lung-pressure-gestures") return (+g[0]).toFixed(0);
  return g[4] && !g[0] ? "" : g[0];
}

const isNeutral = (g: Gesture) => !!g[4];

// the rising curve at a block's left: how it approaches its target (levels off after ~3 τ)
const APPROACH = "M0 96 C 18 40, 45 6, 100 4";

// ---------------------------------------------------------------------------
// Small hooks

function useThemeVersion() {
  const [v, setV] = useState(0);
  useEffect(() => {
    const o = new MutationObserver(() => setV((x) => x + 1));
    o.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => o.disconnect();
  }, []);
  return v;
}

function cssColor(name: string): [number, number, number] {
  const c = document.createElement("canvas").getContext("2d")!;
  c.fillStyle = getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#000";
  c.fillRect(0, 0, 1, 1);
  const d = c.getImageData(0, 0, 1, 1).data;
  return [d[0], d[1], d[2]];
}

let dragCounter = 0;

// ---------------------------------------------------------------------------
// The gestural score

export function ScoreInfo({ t }: { t: T }) {
  const a = useArticulation();
  const s = useScore();
  if (!s) return null;
  const name = s.score.path ? s.score.path.split(/[\\/]/).pop()! : s.id;
  const zoom = (f: number) => articulation.setLocal({ pxs: Math.round(Math.min(ZOOM.max, Math.max(ZOOM.min, a.local.pxs * f))) });
  return (
    <>
      <span className="mono clip" title={s.score.path ?? s.id}>{name} · {s.score.duration.toFixed(2)} s</span>
      <span className="grow" />
      <span className="keep mono">
        {(["spec", "wave"] as const).map((v, i) => (
          <span key={v}>
            {i > 0 && <span className="sep"> / </span>}
            <button className="hbtn" aria-pressed={a.shared.view === v} onClick={() => articulation.set({ view: v })}>{t("score.view." + v)}</button>
          </span>
        ))}
      </span>
      <span className="keep mono">
        <button className="hbtn" title={t("score.zoom_out")} aria-label={t("score.zoom_out")} onClick={() => zoom(1 / 1.5)}>−</button>
        <span>{a.local.pxs} px/s</span>
        <button className="hbtn" title={t("score.zoom_in")} aria-label={t("score.zoom_in")} onClick={() => zoom(1.5)}>+</button>
        <button className="hbtn" onClick={() => window.dispatchEvent(new Event("articulation-fit"))}>{t("score.fit")}</button>
      </span>
    </>
  );
}

export function ScoreView({ t, onOpen }: { t: T; onOpen: () => void }) {
  const c = useClient();
  const a = useArticulation();
  const p = usePlayer();
  const w = useWorkspace();
  const s = useScore();
  const [sound, fresh] = useScoreSound();
  const curves = useScoreCurves();
  const theme = useThemeVersion();
  const tl = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ left: 0, width: 0 });
  const anchor = useRef<{ time: number; x: number } | null>(null);
  const rangeStart = useRef<{ t: number; x: number; moved: boolean } | null>(null);
  const pxs = a.local.pxs;

  // keep the time under the anchor (the pointer, or the middle) where it was when zooming
  const lastPxs = useRef(pxs);
  useLayoutEffect(() => {
    const el = tl.current;
    if (!el || lastPxs.current === pxs) return;
    const old = lastPxs.current;
    lastPxs.current = pxs;
    const x = anchor.current?.x ?? (el.clientWidth - LAB_W) / 2;
    const time = anchor.current?.time ?? (el.scrollLeft + x) / old;
    anchor.current = null;
    el.scrollLeft = Math.max(0, time * pxs - x);
  }, [pxs]);

  useEffect(() => {
    const el = tl.current;
    if (!el) return;
    const update = () => setView({ left: el.scrollLeft, width: el.clientWidth - LAB_W });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    el.addEventListener("scroll", update, { passive: true });
    const wheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      const x = e.clientX - el.getBoundingClientRect().left - LAB_W;
      anchor.current = { x, time: (el.scrollLeft + x) / articulation.local.pxs };
      const f = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      articulation.setLocal({ pxs: Math.round(Math.min(ZOOM.max, Math.max(ZOOM.min, articulation.local.pxs * f))) });
    };
    el.addEventListener("wheel", wheel, { passive: false });
    const fit = () => {
      const d = Object.values(client.project?.scores ?? {})[0]?.duration;
      if (d) { anchor.current = { x: 0, time: 0 }; articulation.setLocal({ pxs: Math.max(ZOOM.min, Math.floor((el.clientWidth - LAB_W - 16) / d)) }); }
    };
    window.addEventListener("articulation-fit", fit);
    return () => { ro.disconnect(); el.removeEventListener("scroll", update); el.removeEventListener("wheel", wheel); window.removeEventListener("articulation-fit", fit); };
  }, [s !== null]); // eslint-disable-line react-hooks/exhaustive-deps

  // while playing, keep the playhead in view
  useEffect(() => {
    const el = tl.current;
    if (!el || p.status !== "playing") return;
    const x = a.shared.time * pxs;
    if (x > el.scrollLeft + el.clientWidth - LAB_W - 24 || x < el.scrollLeft) el.scrollLeft = Math.max(0, x - 24);
  }, [a.shared.time, p.status, pxs]);

  if (!s) {
    return (
      <div className="abody empty">
        <p>{t("score.none")}</p>
        <button className="tbtn primary" onClick={onOpen}>{t("score.open")}…</button>
      </div>
    );
  }
  const score = s.score;
  const dur = Math.max(score.duration, sound?.duration ?? 0);
  const W = Math.ceil(dur * pxs) + 32;
  // the part in view (with a margin), so only that is drawn
  const t0 = Math.max(0, (view.left - 200) / pxs), t1 = (view.left + view.width + 200) / pxs;

  const timeAt = (clientX: number) => {
    const r = tl.current!.getBoundingClientRect();
    return Math.min(dur, Math.max(0, (clientX - r.left - LAB_W + tl.current!.scrollLeft) / pxs));
  };

  // ruler: drag moves the playhead; sound lane: drag selects a range, a click sets the playhead
  const scrub = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    articulation.set({ time: timeAt(e.clientX) });
  };
  const scrubMove = (e: React.PointerEvent) => {
    if ((e.currentTarget as Element).hasPointerCapture(e.pointerId)) articulation.set({ time: timeAt(e.clientX) });
  };
  const rangeDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    rangeStart.current = { t: timeAt(e.clientX), x: e.clientX, moved: false };
  };
  const rangeMove = (e: React.PointerEvent) => {
    const r = rangeStart.current;
    if (!r || !(e.currentTarget as Element).hasPointerCapture(e.pointerId)) return;
    if (Math.abs(e.clientX - r.x) > 3) r.moved = true;
    if (r.moved) { const u = timeAt(e.clientX); articulation.set({ range: [Math.min(r.t, u), Math.max(r.t, u)] }); }
  };
  const rangeUp = () => {
    const r = rangeStart.current;
    rangeStart.current = null;
    if (r && !r.moved) articulation.set({ time: r.t, range: null });
  };

  const rows: ReactNode[] = [];
  const label = (name: string, lane: string | null, unit: string, edited: boolean, resizable: boolean) => {
    const folded = lane !== null && a.local.folded.includes(lane);
    return (
      <div className="lab-c">
        <span className="lt">
          {lane && (
            <button className="fold" title={t(folded ? "score.unfold" : "score.fold")} aria-label={t(folded ? "score.unfold" : "score.fold")}
              aria-expanded={!folded} onClick={() => articulation.toggleFold(lane)}>{folded ? "▸" : "▾"}</button>
          )}
          <span className={"n clip" + (edited ? " edited" : "")} title={name}>{edited ? "● " : ""}{name}</span>
        </span>
        {unit && !folded && <span className="u">{unit}</span>}
        {resizable && !folded && <LaneResizer lane={lane ?? "sound"} t={t} />}
      </div>
    );
  };

  rows.push(
    <div key="ruler" className="tl-row ruler">
      {label("t [s]", null, "", false, false)}
      <div className="track" style={{ width: W, height: RULER_H }}
        onPointerDown={scrub} onPointerMove={scrubMove} title={t("score.ruler")}>
        <Ruler pxs={pxs} dur={dur} t0={t0} t1={t1} W={W} time={a.shared.time} range={a.shared.range} />
      </div>
    </div>,
  );
  const soundFolded = a.local.folded.includes("sound");
  const soundH = soundFolded ? FOLD_H : a.height("sound");
  rows.push(
    <div key="sound" className={"tl-row sound" + (soundFolded ? " folded" : "")}>
      <div className="lab-c">
        <span className="lt">
          <button className="fold" aria-expanded={!soundFolded} title={t(soundFolded ? "score.unfold" : "score.fold")}
            onClick={() => articulation.toggleFold("sound")}>{soundFolded ? "▸" : "▾"}</button>
          <span className="n clip">{t("score.sound")}</span>
        </span>
        {!soundFolded && <span className="u clip" title={w.speaker ?? ""}>{fresh || !s ? w.speaker : t("score.synthesizing")}</span>}
        {!soundFolded && <LaneResizer lane="sound" t={t} />}
      </div>
      <div className="track" style={{ width: W, height: soundH }} title={t("score.sound_hint")}
        onPointerDown={rangeDown} onPointerMove={rangeMove} onPointerUp={rangeUp}>
        {sound && !soundFolded && (a.shared.view === "spec"
          ? <Spectrogram sound={sound} pxs={pxs} left={view.left} width={view.width} height={soundH} theme={theme} />
          : <Waveform sound={sound} pxs={pxs} t0={t0} t1={t1} height={soundH} />)}
        {!fresh && <span className="stale" />}
      </div>
    </div>,
  );

  for (const seq of score.sequences) {
    const type = seq.type;
    const inf = info(score, type);
    const folded = a.local.folded.includes(type);
    const line = LINE_LANES.includes(type);
    const H = folded ? FOLD_H : line ? a.height(type) : LANE_H;
    const edited = c.isEdited(s.id, ["sequence", type]);
    const st = starts(seq.gestures);
    // blocks that differ from the saved score (by time and values) are marked
    const saved = edited ? (c.savedValue(s.id, ["sequence", type]) as Gesture[]) : null;
    const savedKeys = saved ? new Set(starts(saved).map((x, i) => x.toFixed(6) + JSON.stringify(saved[i]))) : null;
    const blocks: ReactNode[] = [];
    seq.gestures.forEach((g, i) => {
      if (st[i] + g[2] < t0 || st[i] > t1) return;
      const wpx = g[2] * pxs;
      const sel = a.shared.sel?.seq === type && a.shared.sel.index === i;
      const text = gestureLabel(type, g);
      const changed = savedKeys !== null && !savedKeys.has(st[i].toFixed(6) + JSON.stringify(g));
      const ap = Math.min(wpx, g[3] * 3 * pxs);
      blocks.push(
        <div key={i} className={"g" + (isNeutral(g) ? " neu" : "") + (sel ? " sel" : "") + (changed ? " edited" : "")}
          style={{ left: st[i] * pxs, width: Math.max(1, wpx) }}
          title={`${isNeutral(g) ? t("score.neutral") + (text ? " · " + text : "") : text} · ${st[i].toFixed(3)}–${(st[i] + g[2]).toFixed(3)} s`}
          onPointerDown={(e) => { if (e.button === 0 && !(e.target as Element).closest(".grip")) articulation.set({ sel: { seq: type, index: i } }); }}>
          {!folded && ap >= 3 && (
            <svg className="ap" width={ap} viewBox="0 0 100 100" preserveAspectRatio="none"><path d={APPROACH} /></svg>
          )}
          {!folded && wpx > 18 && <span className="gt">{text}</span>}
          {!folded && <Grip score={s.id} type={type} index={i} timeAt={timeAt} t={t} />}
        </div>,
      );
    });
    rows.push(
      <div key={type} className={"tl-row" + (line ? " lane-line" : "") + (folded ? " folded" : "")}>
        {label(t("score.lane." + type), type, inf.unit.replace("^2", "²"), edited, line)}
        <div className="track" style={{ width: W, height: H }}>
          {line && !folded && <LineCurve type={type} gestures={seq.gestures} curves={curves} pxs={pxs} t0={t0} t1={t1} H={H} left={view.left} sel={a.shared.sel?.seq === type ? a.shared.sel.index : null} />}
          {blocks}
        </div>
      </div>,
    );
  }

  const range = a.shared.range;
  return (
    <div className="score">
      <div className="tl" ref={tl}>
        <div className="tl-in" style={{ width: LAB_W + W }}>
          {rows}
          {range && <div className="over range" style={{ left: LAB_W + range[0] * pxs, width: (range[1] - range[0]) * pxs, top: RULER_H }} />}
          <div className="over head" style={{ left: LAB_W + a.shared.time * pxs - 1 }} />
        </div>
      </div>
      <Overview sound={sound} dur={dur} view={view} pxs={pxs} time={a.shared.time} range={range}
        onScroll={(x) => { if (tl.current) tl.current.scrollLeft = x; }} t={t} />
    </div>
  );
}

function LaneResizer({ lane, t }: { lane: string; t: T }) {
  const start = useRef<{ y: number; h: number } | null>(null);
  return (
    <span className="rsz" title={t("score.resize")}
      onPointerDown={(e) => {
        e.preventDefault();
        (e.currentTarget as Element).setPointerCapture(e.pointerId);
        start.current = { y: e.clientY, h: articulation.height(lane) };
      }}
      onPointerMove={(e) => {
        const s = start.current;
        if (!s || !(e.currentTarget as Element).hasPointerCapture(e.pointerId)) return;
        const h = Math.round(Math.min(HEIGHT.max, Math.max(HEIGHT.min, s.h + e.clientY - s.y)) / 4) * 4;
        articulation.setLocal({ heights: { ...articulation.local.heights, [lane]: h } });
      }}
      onPointerUp={() => { start.current = null; }} />
  );
}

/** The right edge of a block: drag to move the boundary (one undo step per drag). */
function Grip({ score, type, index, timeAt, t }: {
  score: string; type: string; index: number; timeAt: (x: number) => number; t: T;
}) {
  const d = useRef<{ id: string; frame: number; time: number } | null>(null);
  const send = (time: number, id: string) =>
    client.op("gesture.set_boundary", { score, sequence: type, index, time }, id);
  return (
    <span className="grip" title={t("score.drag_end")}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        e.stopPropagation();
        (e.currentTarget as Element).setPointerCapture(e.pointerId);
        d.current = { id: `gesture/${++dragCounter}`, frame: 0, time: timeAt(e.clientX) };
        articulation.set({ sel: { seq: type, index } });
      }}
      onPointerMove={(e) => {
        const g = d.current;
        if (!g || !(e.currentTarget as Element).hasPointerCapture(e.pointerId)) return;
        g.time = timeAt(e.clientX);
        if (!g.frame) g.frame = requestAnimationFrame(() => { g.frame = 0; void send(g.time, g.id); });
      }}
      onPointerUp={(e) => {
        const g = d.current;
        d.current = null;
        if (!g) return;
        if (g.frame) cancelAnimationFrame(g.frame);
        void send(timeAt(e.clientX), g.id).then(() => client.endDrag(g.id));
      }} />
  );
}

function Ruler({ pxs, dur, t0, t1, W, time, range }: {
  pxs: number; dur: number; t0: number; t1: number; W: number; time: number; range: [number, number] | null;
}) {
  const steps = [0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5];
  const major = steps.find((s) => s * pxs >= 64) ?? 5, minor = steps.find((s) => s * pxs >= 8) ?? 1;
  const ticks: ReactNode[] = [];
  for (let i = Math.floor(t0 / minor); i * minor <= Math.min(dur, t1); i++) {
    const v = i * minor, x = v * pxs;
    const isMajor = Math.abs(v / major - Math.round(v / major)) < 1e-6;
    ticks.push(<line key={"l" + i} className={"tick" + (isMajor ? "" : " minor")} x1={x} x2={x} y1={isMajor ? 10 : 16} y2={24} />);
    if (isMajor) ticks.push(<text key={"t" + i} x={x + 4} y={14}>{v.toFixed(major < 0.01 ? 3 : major < 0.1 ? 2 : 1)}</text>);
  }
  return (
    <svg width={W} height={RULER_H} className="ruler-svg">
      {ticks}
      {range && <rect className="rangebar" x={range[0] * pxs} y={20} width={(range[1] - range[0]) * pxs} height={4} />}
      <path className="headmark" d={`M${time * pxs - 5} 12 h10 l-5 8 z`} />
    </svg>
  );
}

function Waveform({ sound, pxs, t0, t1, height }: { sound: SoundView; pxs: number; t0: number; t1: number; height: number }) {
  const { env } = arrays(sound);
  const { step, count } = sound.envelope;
  const per = Math.max(1, Math.floor(1 / (step * pxs))); // about one bin per pixel
  const m = height / 2 - 2;
  let top = "", bot = "";
  for (let i = Math.max(0, Math.floor(t0 / step)); i < Math.min(count, t1 / step); i += per) {
    let lo = 0, hi = 0;
    for (let j = i; j < Math.min(count, i + per); j++) { lo = Math.min(lo, env[2 * j]); hi = Math.max(hi, env[2 * j + 1]); }
    const x = (i * step * pxs).toFixed(1);
    top += `${x},${(height / 2 - (hi / 127) * m).toFixed(1)} `;
    bot = `${x},${(height / 2 - (lo / 127) * m).toFixed(1)} ` + bot;
  }
  return (
    <svg className="wavesvg" width={sound.duration * pxs + 2} height={height}>
      <line className="wave-axis" x1={0} x2={sound.duration * pxs} y1={height / 2} y2={height / 2} />
      <polygon className="wave" points={top + bot} />
    </svg>
  );
}

/** The spectrogram of the part in view, drawn on a canvas that stays in view (token colours). */
function Spectrogram({ sound, pxs, left, width, height, theme }: {
  sound: SoundView; pxs: number; left: number; width: number; height: number; theme: number;
}) {
  const cv = useRef<HTMLCanvasElement>(null);
  const w = Math.max(1, Math.round(width));
  useEffect(() => {
    const el = cv.current;
    if (!el || width <= 0) return;
    const { spec } = arrays(sound);
    const g = sound.spectrogram;
    el.width = w;
    el.height = height;
    const ctx = el.getContext("2d")!;
    const img = ctx.createImageData(w, height);
    const p = cssColor("--paper"), k = cssColor("--ink");
    for (let x = 0; x < w; x++) {
      const time = (left + x) / pxs;
      const f = Math.round((time - g.start) / g.step);
      const inside = f >= 0 && f < g.frames && time <= sound.duration;
      for (let y = 0; y < height; y++) {
        const b = Math.min(g.bands - 1, Math.floor((1 - y / height) * g.bands));
        const v = inside ? Math.pow(spec[f * g.bands + b] / 255, 1.6) : 0;
        const o = (y * w + x) * 4;
        for (let ch = 0; ch < 3; ch++) img.data[o + ch] = p[ch] + (k[ch] - p[ch]) * v;
        img.data[o + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }, [sound, pxs, left, w, height, theme, width]);
  return <canvas ref={cv} className="speccv" style={{ left, width: w, height }} />;
}

function LineCurve({ type, gestures, curves, pxs, t0, t1, H, left, sel }: {
  type: string; gestures: Gesture[]; curves: Curves | null; pxs: number; t0: number; t1: number; H: number; left: number; sel: number | null;
}) {
  const real = type === "f0-gestures" ? curves?.f0 : curves?.pressure;
  const st = starts(gestures);
  const vals = gestures.flatMap((g) => [+g[0], +g[0] + g[1] * g[2]]);
  if (real) vals.push(...real);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (type === "lung-pressure-gestures") lo = Math.min(lo, 0);
  const pad = (hi - lo) * 0.08 || 1;
  lo -= pad; hi += pad;
  const top = 10, bot = H - BLOCK_H - 4;
  const Y = (v: number) => (top + (1 - (v - lo) / (hi - lo)) * (bot - top)).toFixed(1);
  let target = "";
  gestures.forEach((g, i) => {
    if (st[i] + g[2] < t0 || st[i] > t1) return;
    target += `M${(st[i] * pxs).toFixed(1)} ${Y(+g[0])} L${((st[i] + g[2]) * pxs).toFixed(1)} ${Y(+g[0] + g[1] * g[2])} `;
  });
  let pts = "";
  if (real && curves) {
    const per = Math.max(1, Math.floor(curves.rate / pxs));
    for (let i = Math.max(0, Math.floor(t0 * curves.rate)); i < Math.min(real.length, t1 * curves.rate); i += per)
      pts += `${((i / curves.rate) * pxs).toFixed(1)},${Y(real[i])} `;
  }
  const g = sel !== null ? gestures[sel] : null;
  const fmt = (v: number) => (type === "f0-gestures" ? `${v.toFixed(0)} st · ${Math.pow(2, v / 12).toFixed(0)} Hz` : `${v.toFixed(0)} dPa`);
  return (
    <>
      <svg className="curve" width={(st[st.length - 1] + (gestures.at(-1)?.[2] ?? 0)) * pxs + 2} height={H}>
        <path className="target" d={target} />
        {pts && <polyline className="real" points={pts} />}
        {g && sel !== null && <path className="selline" d={`M${st[sel] * pxs} ${Y(+g[0])} L${(st[sel] + g[2]) * pxs} ${Y(+g[0] + g[1] * g[2])}`} />}
      </svg>
      <span className="scale mono" style={{ left: left + 4 }}>{fmt(hi - pad)}</span>
    </>
  );
}

function Overview({ sound, dur, view, pxs, time, range, onScroll, t }: {
  sound: SoundView | null; dur: number; view: { left: number; width: number }; pxs: number; time: number;
  range: [number, number] | null; onScroll: (x: number) => void; t: T;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(0);
  useEffect(() => {
    const el = box.current!;
    const ro = new ResizeObserver(() => setW(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const H = OVERVIEW_H;
  let poly = "";
  if (sound && W > 0) {
    const { env } = arrays(sound);
    const n = sound.envelope.count, per = n / W;
    let top = "", bot = "";
    for (let x = 0; x < W; x++) {
      let lo = 0, hi = 0;
      for (let j = Math.floor(x * per); j < Math.min(n, Math.max(Math.floor(x * per) + 1, Math.floor((x + 1) * per))); j++) { lo = Math.min(lo, env[2 * j]); hi = Math.max(hi, env[2 * j + 1]); }
      top += `${x},${(H / 2 - (hi / 127) * (H / 2 - 3)).toFixed(1)} `;
      bot = `${x},${(H / 2 - (lo / 127) * (H / 2 - 3)).toFixed(1)} ` + bot;
    }
    poly = top + bot;
  }
  const X = (s: number) => (s / dur) * W;
  const total = dur * pxs + 32;
  const winW = Math.max(8, Math.min(1, view.width / total) * W), winL = (view.left / total) * W;
  const go = (clientX: number) => {
    const r = box.current!.getBoundingClientRect();
    onScroll(((clientX - r.left - winW / 2) / W) * total);
  };
  return (
    <div className="ovw">
      <span className="mono ovw-lab">{t("score.overview")}</span>
      <div className="ovw-box" ref={box} title={t("score.overview_hint")}
        onPointerDown={(e) => { (e.currentTarget as Element).setPointerCapture(e.pointerId); go(e.clientX); }}
        onPointerMove={(e) => { if ((e.currentTarget as Element).hasPointerCapture(e.pointerId)) go(e.clientX); }}>
        <svg width={W} height={H}>
          {poly && <polygon className="ovw-wave" points={poly} />}
          {range && <rect className="rangebar" x={X(range[0])} y={H - 3} width={X(range[1]) - X(range[0])} height={3} />}
          <line className="ovw-head" x1={X(time)} x2={X(time)} y1={0} y2={H} />
        </svg>
        <div className="win" style={{ left: winL, width: winW }} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// The chosen gesture

export function GestureInfo({ t }: { t: T }) {
  const a = useArticulation();
  const s = useScore();
  const sel = a.shared.sel;
  const seq = sel && s?.score.sequences.find((q) => q.type === sel.seq);
  if (!s || !sel || !seq || !seq.gestures[sel.index]) return null;
  const text = t("gesture.which", { lane: t("score.lane." + sel.seq), i: sel.index + 1, n: seq.gestures.length });
  return <span className="mono clip" title={text}>{text}</span>;
}

export function GestureEditor({ t }: { t: T }) {
  const c = useClient();
  const a = useArticulation();
  const w = useWorkspace();
  const s = useScore();
  const sel = a.shared.sel;
  const seq = sel && s?.score.sequences.find((q) => q.type === sel.seq);
  const g = seq && sel ? seq.gestures[sel.index] : null;
  if (!s || !sel || !seq || !g) return <div className="abody empty">{s ? t("gesture.none") : t("score.none")}</div>;
  const inf = info(s.score, sel.seq);
  const st = starts(seq.gestures);
  const start = st[sel.index];
  const next = seq.gestures[sel.index + 1];
  const maxLen = next ? g[2] + next[2] - 0.001 : Math.max(0.5, g[2] * 2);
  const base = { score: s.id, sequence: sel.seq, index: sel.index };
  // a value is marked when it differs from the gesture that started at the same time when saved
  const saved = c.isEdited(s.id, ["sequence", sel.seq]) ? (c.savedValue(s.id, ["sequence", sel.seq]) as Gesture[]) : null;
  const savedG = saved ? saved[starts(saved).findIndex((x) => Math.abs(x - start) < 1e-6)] : g;
  const edited = (k: number) => !savedG || savedG[k] !== g[k];
  const op = (name: string, args: Record<string, unknown>) => client.op(name, args);
  const choose = (index: number) => articulation.set({ sel: { seq: sel.seq, index } });

  // the shapes a value can name: vocal tract shapes, or glottis shapes for the glottis lane
  const sp = w.speaker ? c.project!.speakers[w.speaker] : null;
  const names = !sp ? [] : sel.seq === "glottal-shape-gestures"
    ? Object.keys(sp.glottis.models.find((m) => m.selected)?.shapes ?? {})
    : Object.keys(sp.tract.shapes);
  if (inf.nominal && g[0] && !names.includes(g[0])) names.unshift(g[0]);
  const unit = inf.unit.replace("^2", "²");

  return (
    <div className="params gesture">
      <div className="group">
        {inf.nominal ? (
          <div className="param wide">
            <span className={"mono clip" + (edited(0) ? " edited" : "")}>{t("gesture.value")}</span>
            <select className="pick mono" value={g[0]} title={g[0] || t("score.neutral")}
              onChange={(e) => void op("gesture.set", { ...base, value: e.target.value, neutral: e.target.value === "" })}>
              <option value="">{"— " + t("score.neutral")}</option>
              {names.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
        ) : (
          <ValueRow wide label={t("gesture.value") + (unit ? ` [${unit}]` : "")} min={inf.min} max={inf.max} value={+g[0]}
            edited={edited(0)} op="gesture.set" args={base} />
        )}
        {sel.seq === "f0-gestures" && <p className="mono note-line">≈ {Math.pow(2, +g[0] / 12).toFixed(1)} Hz</p>}
        {sel.seq === "lung-pressure-gestures" && <p className="mono note-line">= {(+g[0] / 10).toFixed(0)} Pa</p>}
        <div className="param wide">
          <span className="mono clip">{t("gesture.neutral")}</span>
          <button className="check mono clip" aria-pressed={!!g[4]} title={t("gesture.neutral_hint")}
            onClick={() => void op("gesture.set", { ...base, neutral: !g[4] })}>
            {g[4] ? t("gesture.neutral_yes") : t("gesture.neutral_no")}
          </button>
        </div>
      </div>
      <div className="group">
        <div className="param wide">
          <span className="mono clip" title={t("gesture.start_hint")}>{t("gesture.start")} [s]</span>
          <span />
          <span className="v ro" title={t("gesture.start_hint")}>{start.toFixed(3)}</span>
        </div>
        <ValueRow wide label={t("gesture.length") + " [s]"} min={0.001} max={maxLen} value={g[2]} edited={edited(2)}
          op="gesture.set_boundary" args={base} field="time" map={(v) => start + v} />
        <ValueRow wide label={t("gesture.tau") + " [s]"} min={inf.min_tau} max={inf.max_tau} value={g[3]} edited={edited(3)}
          op="gesture.set" args={base} field="time_constant" />
        {inf.max_slope > inf.min_slope && (
          <ValueRow wide label={t("gesture.slope") + ` [${unit}/s]`} min={inf.min_slope} max={inf.max_slope} value={g[1]} edited={edited(1)}
            op="gesture.set" args={base} field="slope" />
        )}
      </div>
      <p className="hint">
        <svg width="20" height="12" viewBox="0 0 100 100" preserveAspectRatio="none" className="aplegend"><path d={APPROACH} /></svg>
        {t("gesture.approach_hint")}
      </p>
      <div className="cmds">
        <button className="tbtn" disabled={sel.index === 0} onClick={() => choose(sel.index - 1)}>◂ {t("gesture.prev")}</button>
        <button className="tbtn" disabled={sel.index >= seq.gestures.length - 1} onClick={() => choose(sel.index + 1)}>{t("gesture.next")} ▸</button>
        <button className="tbtn" onClick={() => void client.request<number>("op", { op: "gesture.split", args: { score: s.id, sequence: sel.seq, time: a.shared.time } })
          .then((i: number) => choose(i)).catch((e: Error) => client.report(e))}>{t("gesture.split")}</button>
        <button className="tbtn" onClick={() => void client.request<number>("op", { op: "gesture.add", args: { score: s.id, sequence: sel.seq, time: a.shared.time } })
          .then((i: number) => choose(i)).catch((e: Error) => client.report(e))}>{t("gesture.add")}</button>
        <button className="tbtn danger" disabled={seq.gestures.length <= 1}
          onClick={() => void op("gesture.delete", base).then(() => choose(Math.max(0, sel.index - 1)))}>{t("gesture.delete")}</button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// The vocal tract and the area function at the playhead

export function PlayheadInfo({ t }: { t: T }) {
  const a = useArticulation();
  return <span className="mono clip">{t("score.at", { t: a.shared.time.toFixed(3) })}</span>;
}

export function TractAtPlayhead({ t }: { t: T }) {
  const w = useWorkspace();
  const s = useScore();
  const cur = useTractAtPlayhead();
  if (!s || !w.speaker) return <div className="abody empty">{t("score.none")}</div>;
  return <TractView speaker={"score:" + w.speaker} cur={cur} saved={null} t={t} />;
}

export function AreaAtPlayhead({ t }: { t: T }) {
  const s = useScore();
  const cur = useTractAtPlayhead();
  if (!s) return <div className="abody empty">{t("score.none")}</div>;
  return <AreaPlot cur={cur} saved={null} t={t} />;
}

// ---------------------------------------------------------------------------
// Opening a score

export function OpenScoreDialog({ t, onClose, onDone }: { t: T; onClose: () => void; onDone: (id: string) => void }) {
  const [path, setPath] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [unsaved, setUnsaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { input.current!.focus(); }, []);
  const submit = async () => {
    setBusy(true);
    try {
      onDone(await client.openScore(path.trim(), unsaved));
    } catch (e) {
      const m = (e as Error).message;
      if (m.includes("unsaved changes")) setUnsaved(true); else setError(m);
    } finally { setBusy(false); }
  };
  return createPortal(
    <div className="scrim" onPointerDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <form className="dialog" role="dialog" aria-modal="true" aria-label={t("score.open_title")}
        onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}
        onSubmit={(e) => { e.preventDefault(); if (!busy && path.trim()) void submit(); }}>
        <h2 className="clip">{t("score.open_title")}</h2>
        <label className="field">
          <span className="mono">{t("score.open_path")}</span>
          <input ref={input} className="mono" value={path} spellCheck={false} placeholder="…/utterance.ges"
            onChange={(e) => { setPath(e.target.value); setError(null); setUnsaved(false); }} />
        </label>
        {unsaved && <p className="msg">{t("score.open_unsaved")}</p>}
        {error && <p className="msg err">{t("note.error", { message: error })}</p>}
        <div className="actions">
          <button type="button" className="tbtn" onClick={onClose}>{t("save.cancel")}</button>
          <button type="submit" className={"tbtn primary" + (unsaved ? " danger" : "")} disabled={busy || !path.trim()}>
            {unsaved ? t("score.open_discard") : t("score.open")}
          </button>
        </div>
      </form>
    </div>,
    document.body,
  );
}
