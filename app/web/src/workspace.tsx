// What the editors of a window share: the selected speaker and shape, and the
// VTL results for that shape. The selection is view state (not in the undo
// history); windows of the same browser share it over a BroadcastChannel, so
// a parameter panel in its own window follows the shape chosen in the main one.

import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useComputed, type Computed } from "./compute";
import { useClient } from "./store";

export const FMAX = 5000;

export interface WorkspaceData {
  speakers: string[];
  speaker: string | null;
  setSpeaker: (s: string) => void;
  shapeNames: string[];
  shape: string | null;
  setShape: (s: string) => void;
  editedShapes: Set<string>;
  cur: Computed | null;
  saved: Computed | null; // the shape as saved, when it has edits
}

const Ctx = createContext<WorkspaceData | null>(null);

export function useWorkspace(): WorkspaceData {
  const w = useContext(Ctx);
  if (!w) throw new Error("useWorkspace outside WorkspaceProvider");
  return w;
}

type Selection = { speaker: string | null; shape: string | null };
const KEY = "ui.selection";

function useSharedSelection() {
  const [sel, setSel] = useState<Selection>(() => {
    try { return JSON.parse(sessionStorage.getItem(KEY) ?? "") as Selection; } catch { return { speaker: null, shape: null }; }
  });
  const chan = useRef<BroadcastChannel | null>(null);
  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const ch = new BroadcastChannel(KEY);
    chan.current = ch;
    ch.onmessage = (e) => setSel(e.data as Selection);
    ch.postMessage({ hello: true });
    return () => ch.close();
  }, []);
  // A new window asks for the selection; the others answer with theirs.
  useEffect(() => {
    const ch = chan.current;
    if (!ch) return;
    ch.onmessage = (e) => {
      if ((e.data as { hello?: boolean }).hello) { if (sel.speaker) ch.postMessage(sel); return; }
      setSel(e.data as Selection);
    };
  }, [sel]);
  const update = (s: Selection) => {
    setSel(s);
    try { sessionStorage.setItem(KEY, JSON.stringify(s)); } catch { /* ignore */ }
    chan.current?.postMessage(s);
  };
  return [sel, update] as const;
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const c = useClient();
  const [sel, setSel] = useSharedSelection();
  const speakers = c.project ? Object.keys(c.project.speakers) : [];
  const speaker = sel.speaker && speakers.includes(sel.speaker) ? sel.speaker : speakers[0] ?? null;
  const sp = speaker ? c.project!.speakers[speaker] : null;
  const shapeNames = sp ? Object.keys(sp.tract.shapes) : [];
  const shape = sel.shape && shapeNames.includes(sel.shape) ? sel.shape : shapeNames[0] ?? null;

  const params = sp && shape ? [...sp.tract.shapes[shape]] : null;
  const savedParams = useMemo(() => {
    if (!sp || !shape || !params || !speaker) return null;
    let any = false;
    const out = sp.tract.params.map((p, i) => {
      const a = ["tract_shape", shape, p.name];
      if (c.isEdited(speaker, a)) { any = true; return c.savedValue(speaker, a) as number; }
      return params[i];
    });
    return any ? out : null;
  }, [c.version, speaker, shape]); // eslint-disable-line react-hooks/exhaustive-deps

  const cur = useComputed(speaker, params, ["tube", "formants", "spectrum", "contours"], FMAX);
  const saved = useComputed(speaker, savedParams, ["tube", "spectrum", "contours"], FMAX);
  const editedShapes = new Set(
    speaker ? c.editedAddresses(speaker).filter((a) => a[0] === "tract_shape").map((a) => a[1] as string) : [],
  );

  const value: WorkspaceData = {
    speakers, speaker, shapeNames, shape, editedShapes, cur, saved,
    setSpeaker: (s) => setSel({ speaker: s, shape: null }),
    setShape: (s) => setSel({ speaker, shape: s }),
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
