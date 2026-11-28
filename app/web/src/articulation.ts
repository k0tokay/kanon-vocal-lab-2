// What the editors of the articulation workspace share: the playhead, the
// selected time range and gesture, and how the score is shown. All of it is
// view state: never in the undo history, never saved with the score.
//
// The playhead, range, selection and the sound view (spectrogram / waveform)
// follow across the windows of this browser (BroadcastChannel), so a vocal
// tract area in its own window shows the time chosen in the main one. Zoom,
// lane heights and folds belong to the window and are remembered in
// localStorage.

import { useSyncExternalStore } from "react";

export const SEQUENCE_TYPES = [
  "vowel-gestures", "lip-gestures", "tongue-tip-gestures", "tongue-body-gestures",
  "velic-gestures", "glottal-shape-gestures", "f0-gestures", "lung-pressure-gestures",
] as const;
/** Lanes drawn with a line for their value; their height (and the sound's) can be dragged. */
export const LINE_LANES = ["f0-gestures", "lung-pressure-gestures"];

export interface Shared {
  time: number;
  range: [number, number] | null;
  sel: { seq: string; index: number } | null;
  view: "spec" | "wave";
}
export interface Local {
  pxs: number; // pixels per second
  heights: Record<string, number>; // "sound" and the line lanes
  folded: string[];
}

const CHANNEL = "ui.articulation";
const LOCAL = "ui.articulation.view";
export const ZOOM = { min: 20, max: 4000 };
export const HEIGHT = { min: 40, max: 320, sound: 96, line: 72 };

function loadLocal(): Local {
  const d: Local = { pxs: 400, heights: {}, folded: [] };
  try {
    const v = JSON.parse(localStorage.getItem(LOCAL) ?? "null");
    if (v && typeof v.pxs === "number") return { ...d, ...v };
  } catch { /* ignore */ }
  return d;
}

function loadShared(): Shared {
  const d: Shared = { time: 0, range: null, sel: null, view: "spec" };
  try {
    const v = JSON.parse(sessionStorage.getItem(CHANNEL) ?? "null");
    if (v && typeof v.time === "number") return { ...d, ...v };
  } catch { /* ignore */ }
  return d;
}

class ArticulationView {
  shared: Shared = loadShared();
  local: Local = loadLocal();
  version = 0;
  private listeners = new Set<() => void>();
  private chan: BroadcastChannel | null = null;

  constructor() {
    if (typeof BroadcastChannel === "undefined") return;
    const ch = (this.chan = new BroadcastChannel(CHANNEL));
    ch.onmessage = (e) => {
      const m = e.data as { hello?: boolean; shared?: Shared };
      if (m.hello) { ch.postMessage({ shared: this.shared }); return; }
      if (m.shared) { this.shared = m.shared; this.changed(); }
    };
    ch.postMessage({ hello: true }); // a new window asks the others for theirs
  }

  subscribe = (f: () => void) => { this.listeners.add(f); return () => { this.listeners.delete(f); }; };
  private changed() { this.version++; this.listeners.forEach((f) => f()); }

  set(p: Partial<Shared>) {
    this.shared = { ...this.shared, ...p };
    try { sessionStorage.setItem(CHANNEL, JSON.stringify(this.shared)); } catch { /* ignore */ }
    this.chan?.postMessage({ shared: this.shared });
    this.changed();
  }

  setLocal(p: Partial<Local>) {
    this.local = { ...this.local, ...p };
    try { localStorage.setItem(LOCAL, JSON.stringify(this.local)); } catch { /* ignore */ }
    this.changed();
  }

  height(lane: string) {
    return this.local.heights[lane] ?? (lane === "sound" ? HEIGHT.sound : HEIGHT.line);
  }

  toggleFold(lane: string) {
    const f = new Set(this.local.folded);
    if (f.has(lane)) f.delete(lane); else f.add(lane);
    this.setLocal({ folded: [...f] });
  }
}

export const articulation = new ArticulationView();

export function useArticulation(): ArticulationView {
  useSyncExternalStore(articulation.subscribe, () => articulation.version);
  return articulation;
}
