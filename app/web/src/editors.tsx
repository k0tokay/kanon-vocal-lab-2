// The kinds of editor an area can show. Adding a kind (the glottis and
// articulation editors of the next stages) is adding an entry here and its
// name to the translation files ("ed.<id>").

import type { ReactNode } from "react";
import type { T } from "./i18n";
import { useClient } from "./store";
import { FMAX, useWorkspace } from "./workspace";
import { Params } from "./components/Params";
import { AreaPlot, SpectrumPlot, TractView } from "./components/plots";
import { ShapeList } from "./components/Shapes";
import { GShapeList, GShapeParams, ModelList, StaticParams, WaveView, useGlottisWave } from "./components/Glottis";

export interface EditorKind {
  id: string;
  /** The standard workspace it belongs to ("ws.<group>" names it in the editor menu). */
  group: "tract" | "glottis";
  /** Smallest body size in px (the 32 px header comes on top). */
  min: { w: number; h: number };
  /** Text right of the editor name in the header (cut with … when narrow). */
  Info?: (p: { t: T }) => ReactNode;
  Body: (p: { t: T }) => ReactNode;
}

const HEADER = 32;

function Empty({ t }: { t: T }) {
  const c = useClient();
  return <div className="abody empty">{c.project ? t("no_speaker") : t("loading")}</div>;
}

const clip = (text: string) => <span className="mono clip" title={text}>{text}</span>;

export const EDITORS: EditorKind[] = [
  {
    id: "tract",
    group: "tract",
    min: { w: 160, h: 120 },
    Info: () => {
      const w = useWorkspace();
      return w.speaker && w.shape ? clip(`${w.speaker} · ${w.shape}`) : null;
    },
    Body: ({ t }) => {
      const w = useWorkspace();
      return w.speaker ? <TractView speaker={w.speaker} cur={w.cur} saved={w.saved} t={t} /> : <Empty t={t} />;
    },
  },
  {
    id: "area",
    group: "tract",
    min: { w: 160, h: 96 },
    Info: ({ t }) => clip(`${t("ax.area")} × cm`),
    Body: ({ t }) => {
      const w = useWorkspace();
      return w.speaker ? <AreaPlot cur={w.cur} saved={w.saved} t={t} /> : <Empty t={t} />;
    },
  },
  {
    id: "spectrum",
    group: "tract",
    min: { w: 160, h: 96 },
    Info: () => {
      const w = useWorkspace();
      return clip(w.cur?.formants?.slice(0, 3).map((f, i) => `F${i + 1} ${f.toFixed(0)}`).join(" · ") ?? "");
    },
    Body: ({ t }) => {
      const w = useWorkspace();
      return w.speaker ? <SpectrumPlot cur={w.cur} saved={w.saved} fmax={FMAX} /> : <Empty t={t} />;
    },
  },
  {
    id: "shapes",
    group: "tract",
    min: { w: 160, h: 72 },
    Info: () => {
      const w = useWorkspace();
      if (!w.speaker) return null;
      return (
        <>
          {w.speakers.length > 1 && (
            // Cycles through the open speakers; a proper picker comes with the speaker workspace.
            <button className="toggle mono clip" title={w.speaker}
              onClick={() => w.setSpeaker(w.speakers[(w.speakers.indexOf(w.speaker!) + 1) % w.speakers.length])}>
              {w.speaker} ▸
            </button>
          )}
          <span className="mono">{w.shapeNames.length}</span>
        </>
      );
    },
    Body: ({ t }) => {
      const w = useWorkspace();
      if (!w.speaker) return <Empty t={t} />;
      return <ShapeList t={t} speaker={w.speaker} kind="tract" names={w.shapeNames} selected={w.shape}
        edited={w.editedShapes} onSelect={w.setShape} />;
    },
  },
  {
    id: "params",
    group: "tract",
    min: { w: 200, h: 96 },
    Info: () => {
      const w = useWorkspace();
      return w.shape ? clip(w.shape) : null;
    },
    Body: ({ t }) => {
      const w = useWorkspace();
      return w.speaker && w.shape ? <Params speaker={w.speaker} shape={w.shape} t={t} /> : <Empty t={t} />;
    },
  },
  // -- the glottis workspace ---------------------------------------------------
  {
    id: "gmodels",
    group: "glottis",
    min: { w: 200, h: 72 },
    Info: () => {
      const w = useWorkspace();
      return w.speaker ? clip(w.speaker) : null;
    },
    Body: ({ t }) => {
      const w = useWorkspace();
      return w.speaker ? <ModelList t={t} /> : <Empty t={t} />;
    },
  },
  {
    id: "gstatic",
    group: "glottis",
    min: { w: 240, h: 96 },
    Info: () => {
      const w = useWorkspace();
      return w.glottis ? clip(w.glottis.type) : null;
    },
    Body: ({ t }) => {
      const w = useWorkspace();
      return w.glottis ? <StaticParams /> : <Empty t={t} />;
    },
  },
  {
    id: "gshapes",
    group: "glottis",
    min: { w: 160, h: 72 },
    Info: () => {
      const w = useWorkspace();
      return w.glottis ? <span className="mono">{w.gshapeNames.length}</span> : null;
    },
    Body: ({ t }) => {
      const w = useWorkspace();
      return w.glottis ? <GShapeList t={t} /> : <Empty t={t} />;
    },
  },
  {
    id: "gparams",
    group: "glottis",
    min: { w: 240, h: 96 },
    Info: () => {
      const w = useWorkspace();
      return w.gshape ? clip(w.gshape) : null;
    },
    Body: ({ t }) => {
      const w = useWorkspace();
      return w.glottis && w.gshape ? <GShapeParams /> : <Empty t={t} />;
    },
  },
  {
    id: "gwave",
    group: "glottis",
    min: { w: 240, h: 160 },
    Info: ({ t }) => {
      const w = useWorkspace();
      return w.gshape && w.shape ? clip(t("wave.info", { glottis: w.gshape, tract: w.shape })) : null;
    },
    Body: ({ t }) => {
      const w = useWorkspace();
      return w.glottis ? <GlottisWaveBody t={t} /> : <Empty t={t} />;
    },
  },
];

function GlottisWaveBody({ t }: { t: T }) {
  return <WaveView wave={useGlottisWave()} t={t} />;
}

export const EDITOR_IDS = new Set(EDITORS.map((e) => e.id));

export function editorKind(id: string): EditorKind {
  return EDITORS.find((e) => e.id === id) ?? EDITORS[0];
}

/** Minimum size of an area showing this editor, header included. */
export function editorMin(id: string) {
  const m = editorKind(id).min;
  return { w: m.w, h: m.h + HEADER };
}
