import { useEffect, useMemo, useState } from "react";
import { useComputed } from "./compute";
import { LOCALES, setLang, useT, type T } from "./i18n";
import { client, useClient } from "./store";
import { Params } from "./components/Params";
import { AreaPlot, SpectrumPlot, TractView } from "./components/plots";

const WORKSPACES = ["tract", "glottis", "articulation", "speak", "sing", "compare"];
const FMAX = 5000;

// ---------------------------------------------------------------------------
// Theme (remembered per browser)

function initialTheme(): "light" | "dark" {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function useTheme() {
  const [theme, setTheme] = useState(initialTheme);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("ui.theme", theme); } catch { /* ignore */ }
  }, [theme]);
  return [theme, setTheme] as const;
}

// ---------------------------------------------------------------------------
// A short message in a floating layer

function useNote() {
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);
  useEffect(() => {
    if (!note) return;
    const id = setTimeout(() => setNote(null), 3000);
    return () => clearTimeout(id);
  }, [note]);
  return [note, (text: string, error = false) => setNote({ text, error })] as const;
}

// ---------------------------------------------------------------------------

export function App() {
  const c = useClient();
  const [t, lang] = useT();
  const [theme, setTheme] = useTheme();
  const [note, show] = useNote();
  const notYet = (what: string) => show(t("note.not_yet", { what }));

  useEffect(() => {
    const f = (m: string) => show(t("note.error", { message: m }), true);
    c.errors.add(f);
    return () => { c.errors.delete(f); };
  }, [c, t]); // eslint-disable-line react-hooks/exhaustive-deps

  // Undo and redo from the keyboard, except while typing in a field.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "z") return;
      if ((e.target as HTMLElement).closest("input, textarea")) return;
      e.preventDefault();
      void (e.shiftKey ? client.redo() : client.undo());
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const speakers = c.project ? Object.keys(c.project.speakers) : [];
  const [speakerSel, setSpeaker] = useState<string | null>(null);
  const speaker = speakerSel && speakers.includes(speakerSel) ? speakerSel : speakers[0] ?? null;
  const sp = speaker ? c.project!.speakers[speaker] : null;
  const shapeNames = sp ? Object.keys(sp.tract.shapes) : [];
  const [shapeSel, setShape] = useState<string | null>(null);
  const shape = shapeSel && shapeNames.includes(shapeSel) ? shapeSel : shapeNames[0] ?? null;

  // Current parameters, and the saved ones when the shape has edits (drawn dashed).
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
  const ref = useComputed(speaker, savedParams, ["tube", "spectrum", "contours"], FMAX);
  const editedShapes = new Set(
    speaker ? c.editedAddresses(speaker).filter((a) => a[0] === "tract_shape").map((a) => a[1] as string) : [],
  );
  const formants = cur?.formants?.slice(0, 3).map((f, i) => `F${i + 1} ${f.toFixed(0)}`).join(" · ") ?? "";
  const h = c.project?.history;

  return (
    <>
      <header className="top">
        <span className="app" title={c.app}>{c.app || " "}</span>
        <nav className="tabs">
          {WORKSPACES.map((w) => (
            <button key={w} className="tab" aria-selected={w === "tract"}
              title={t("ws." + w)} onClick={() => { if (w !== "tract") notYet(t("ws." + w)); }}>{t("ws." + w)}</button>
          ))}
        </nav>
        <div className="toggles">
          <span>
            {LOCALES.map((l, i) => (
              <span key={l.code}>
                {i > 0 && <span className="sep"> / </span>}
                <button className="toggle" aria-pressed={l.code === lang} onClick={() => setLang(l.code)}>{l.name}</button>
              </span>
            ))}
          </span>
          <span>
            {(["light", "dark"] as const).map((m, i) => (
              <span key={m}>
                {i > 0 && <span className="sep"> / </span>}
                <button className="toggle" aria-pressed={m === theme} onClick={() => setTheme(m)}>{t("theme." + m)}</button>
              </span>
            ))}
          </span>
        </div>
      </header>

      <main className="main">
        {!sp || !shape || !speaker ? (
          <div className="empty" style={{ gridColumn: "1 / 4", gridRow: "1 / 4" }}>
            {c.project ? t("no_speaker") : t("loading")}
          </div>
        ) : (
          <>
            <section className="area" style={{ gridColumn: 1, gridRow: 1 }}>
              <div className="ahead">
                <button className="etype" title={t("ed.tract")} onClick={() => notYet(t("note.editor_menu"))}>{t("ed.tract")}</button>
                <span className="mono clip" title={`${speaker} · ${shape}`}>{speaker} · {shape}</span>
              </div>
              <TractView speaker={speaker} cur={cur} saved={ref} t={t} />
            </section>
            <div className="split-v" />
            <div className="split-h" />
            <div className="bottom-pair">
              <section className="area">
                <div className="ahead">
                  <button className="etype" title={t("ed.area")} onClick={() => notYet(t("note.editor_menu"))}>{t("ed.area")}</button>
                  <span className="grow" />
                  <span className="mono clip" title={`${t("ax.area")} × cm`}>{t("ax.area")} × cm</span>
                </div>
                <AreaPlot cur={cur} saved={ref} t={t} />
              </section>
              <div className="bar" />
              <section className="area">
                <div className="ahead">
                  <button className="etype" title={t("ed.spectrum")} onClick={() => notYet(t("note.editor_menu"))}>{t("ed.spectrum")}</button>
                  <span className="grow" />
                  <span className="mono clip" title={formants}>{formants}</span>
                </div>
                <SpectrumPlot cur={cur} saved={ref} fmax={FMAX} />
              </section>
            </div>
            <aside className="side-col">
              <div className="ahead">
                <button className="etype" title={t("ed.shapes")} onClick={() => notYet(t("note.editor_menu"))}>{t("ed.shapes")}</button>
                <span className="grow" />
                {speakers.length > 1 && <SpeakerPicker speakers={speakers} value={speaker} onChange={setSpeaker} />}
                <span className="mono">{shapeNames.length}</span>
              </div>
              <div className="list">
                {shapeNames.map((n) => (
                  <button key={n} className={"row" + (n === shape ? " sel" : "") + (editedShapes.has(n) ? " edited" : "")}
                    onClick={() => setShape(n)}>
                    <span className="mono mark">{editedShapes.has(n) ? "●" : ""}</span>
                    <span className="name" title={n}>{n}</span>
                  </button>
                ))}
              </div>
              <div className="ahead">
                <button className="etype" title={t("ed.params")} onClick={() => notYet(t("note.editor_menu"))}>{t("ed.params")}</button>
                <span className="grow" />
                <span className="mono clip" title={shape}>{shape}</span>
              </div>
              <Params speaker={speaker} shape={shape} t={t} />
            </aside>
          </>
        )}
      </main>

      <StatusBar t={t} speaker={speaker} onPlay={() => notYet(t("note.play"))}
        canUndo={!!h?.can_undo} canRedo={!!h?.can_redo} undoLabel={h?.undo_label} redoLabel={h?.redo_label} />

      {note && <div className={"note" + (note.error ? " err" : "")} role="status">{note.text}</div>}
    </>
  );
}

function SpeakerPicker({ speakers, value, onChange }: { speakers: string[]; value: string; onChange: (s: string) => void }) {
  // Cycles through the open speakers; a proper picker comes with the speaker workspace.
  return (
    <button className="toggle mono clip" title={value} onClick={() => onChange(speakers[(speakers.indexOf(value) + 1) % speakers.length])}>
      {value} ▸
    </button>
  );
}

function StatusBar({ t, speaker, onPlay, canUndo, canRedo, undoLabel, redoLabel }: {
  t: T; speaker: string | null; onPlay: () => void; canUndo: boolean; canRedo: boolean;
  undoLabel?: string | null; redoLabel?: string | null;
}) {
  const c = useClient();
  const n = c.editedCount();
  const status = (n ? t("status.unsaved", { n }) : t("status.saved")) + (speaker ? " · " + t("status.speaker", { name: speaker }) : "");
  return (
    <footer className="status">
      <button className="tbtn" onClick={onPlay} title={t("play")} aria-label={t("play")}>▶</button>
      <span className="mono">0.000 s</span>
      <button className="tbtn" disabled={!canUndo} onClick={() => void c.undo()}
        title={undoLabel ? t("undo.what", { label: undoLabel }) : undefined}>{t("undo")}</button>
      <button className="tbtn" disabled={!canRedo} onClick={() => void c.redo()}
        title={redoLabel ? t("redo.what", { label: redoLabel }) : undefined}>{t("redo")}</button>
      <span className="grow" />
      {c.status !== "open" ? (
        <span className={"mono clip" + (c.status === "closed" ? " err" : "")}>{t(c.status === "connecting" ? "status.connecting" : "status.disconnected")}</span>
      ) : (
        <span className="mono clip" title={status}>{status}</span>
      )}
    </footer>
  );
}
