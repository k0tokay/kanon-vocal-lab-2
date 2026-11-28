import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { EDITOR_IDS } from "./editors";
import { LOCALES, setLang, useT, type T } from "./i18n";
import { defaultLayout, leaves, loadLayout, newId, removeArea, saveLayout, setEditor, type Leaf, type Node } from "./layout";
import { player, usePlayer } from "./player";
import { client, useClient } from "./store";
import { WorkspaceProvider, useWorkspace } from "./workspace";
import { AreaView, LayoutProvider, NodeView } from "./components/Areas";
import { SaveDialog, refusalNote, suggestName } from "./components/SaveDialog";

const WORKSPACES = ["tract", "glottis", "articulation", "speak", "sing", "compare"];
const READY = new Set(["tract", "glottis"]); // workspaces with editors so far

// A detached area is this page with ?editor=<kind> (and the workspace).
const query = new URLSearchParams(location.search);
const DETACHED = query.get("editor");
const WORKSPACE = query.get("ws") ?? "tract";

// ---------------------------------------------------------------------------
// Theme (remembered per browser; other windows follow through the storage event)

function useTheme() {
  const [theme, setTheme] = useState<"light" | "dark">(
    document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("ui.theme", theme); } catch { /* ignore */ }
  }, [theme]);
  useEffect(() => {
    const f = (e: StorageEvent) => {
      if (e.key === "ui.theme" && (e.newValue === "light" || e.newValue === "dark")) setTheme(e.newValue);
      if (e.key === "ui.lang" && e.newValue) setLang(e.newValue);
    };
    window.addEventListener("storage", f);
    return () => window.removeEventListener("storage", f);
  }, []);
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
  const show = useCallback((text: string, error = false) => setNote({ text, error }), []);
  return [note, show] as const;
}

// ---------------------------------------------------------------------------

export function App() {
  const c = useClient();
  const [t, lang] = useT();
  const [theme, setTheme] = useTheme();
  const [note, show] = useNote();

  useEffect(() => {
    const f = (m: string) => show(t("note.error", { message: m }), true);
    c.errors.add(f);
    return () => { c.errors.delete(f); };
  }, [c, t, show]);

  const [ws, setWs] = useState(READY.has(WORKSPACE) ? WORKSPACE : "tract");
  const go = (w: string) => {
    if (w === ws) return;
    if (!READY.has(w)) { show(t("note.not_yet", { what: t("ws." + w) })); return; }
    setWs(w);
    // the address names the workspace (no reload: the data and the selection stay)
    history.replaceState(null, "", w === "tract" ? location.pathname : `?ws=${encodeURIComponent(w)}`);
  };
  useEffect(() => { if (!DETACHED && c.app) document.title = c.app; }, [c.app]);

  const noteView = note && <div className={"note" + (note.error ? " err" : "")} role="status">{note.text}</div>;

  if (DETACHED) return <Detached t={t} editor={DETACHED} onNote={show} note={noteView} />;

  return (
    <WorkspaceProvider>
      <div className="app-grid">
        <header className="top">
          <span className="app" title={c.app}>{c.app || " "}</span>
          <nav className="tabs">
            {WORKSPACES.map((w) => (
              <button key={w} className="tab" aria-selected={w === ws}
                title={t("ws." + w)} onClick={() => go(w)}>
                {t("ws." + w)}
              </button>
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
        <Layout key={ws} workspace={ws} t={t} onNote={show} />
        <Commands t={t} onNote={show} workspace={ws} />
      </div>
      {noteView}
    </WorkspaceProvider>
  );
}

function Layout({ workspace, t, onNote }: { workspace: string; t: T; onNote: (s: string, e?: boolean) => void }) {
  const [root, setRoot] = useState<Node>(() => loadLayout(workspace, EDITOR_IDS));
  useEffect(() => saveLayout(workspace, root), [workspace, root]);
  const actions = {
    root,
    workspace,
    set: setRoot,
    reset: () => setRoot(defaultLayout(workspace)),
    setEditor: (a: Leaf, editor: string) => setRoot((r) => setEditor(r, a.id, editor)),
    detach: (a: Leaf, rect: DOMRect) => {
      const url = `${location.pathname}?ws=${encodeURIComponent(workspace)}&editor=${encodeURIComponent(a.editor)}`;
      const w = window.open(url, `area-${newId()}`,
        `popup,width=${Math.round(Math.max(rect.width, 320))},height=${Math.round(Math.max(rect.height, 240))}`);
      if (!w) { onNote(t("note.popup_blocked"), true); return; }
      // The area moves to the new window; the last area of the workspace stays.
      if (leaves(root).length > 1) setRoot((r) => removeArea(r, a.id));
    },
  };
  return (
    <LayoutProvider value={actions}>
      <main className="main"><NodeView node={root} t={t} onNote={onNote} /></main>
    </LayoutProvider>
  );
}

function Detached({ t, editor, onNote, note }: { t: T; editor: string; onNote: (s: string, e?: boolean) => void; note: ReactNode }) {
  const [area, setArea] = useState<Leaf>({ type: "area", id: "detached", editor: EDITOR_IDS.has(editor) ? editor : "tract" });
  useEffect(() => { document.title = t("ed." + area.editor); }, [t, area.editor]);
  const actions = {
    root: null,
    workspace: WORKSPACE,
    set: () => {},
    reset: () => {},
    detach: () => {},
    setEditor: (_: Leaf, e: string) => {
      setArea((a) => ({ ...a, editor: e }));
      history.replaceState(null, "", `?ws=${encodeURIComponent(WORKSPACE)}&editor=${encodeURIComponent(e)}`);
    },
  };
  return (
    <WorkspaceProvider>
      <LayoutProvider value={actions}>
        <div className="detached"><AreaView area={area} t={t} onNote={onNote} /></div>
        <Commands t={t} onNote={onNote} bar={false} workspace={WORKSPACE} />
      </LayoutProvider>
      {note}
    </WorkspaceProvider>
  );
}

// ---------------------------------------------------------------------------
// Commands of a window: play / stop, save / save as, undo / redo, from the
// status bar and the keyboard. A detached window has the keys but no bar.

function Commands({ t, onNote, workspace, bar = true }: {
  t: T; onNote: (s: string, e?: boolean) => void; workspace: string; bar?: boolean;
}) {
  const c = useClient();
  const w = useWorkspace();
  const p = usePlayer();
  const [dialog, setDialog] = useState<string | null>(null); // initial path of "save as"
  const sp = w.speaker ? c.project?.speakers[w.speaker] : undefined;

  const play = () => {
    if (p.status !== "idle") { player.stop(); return; }
    if (!w.speaker || !w.shape || !sp) return;
    // the values on screen now, edits included; in the glottis workspace with the chosen glottis shape
    const g = workspace === "glottis" ? w.gshape ?? undefined : undefined;
    player.play(w.speaker, [...sp.tract.shapes[w.shape]], 1.0, g)
      .catch((e: Error) => onNote(t("note.play_failed", { message: e.message }), true));
  };
  const saveAs = () => { if (w.speaker) setDialog(suggestName(sp?.path ?? null, w.speaker)); };
  const save = async () => {
    if (!w.speaker) return;
    try {
      const r = await c.save(w.speaker);
      if (r.ok) { onNote(t("note.saved", { path: r.path })); return; }
      onNote(refusalNote(t, r as typeof r & { ok: false }), true);
      saveAs();
    } catch (e) { c.report(e as Error); }
  };

  // keys: Space plays / stops, Cmd/Ctrl+S saves, +Shift saves as, Cmd/Ctrl+Z undoes
  const latest = useRef({ play, save, saveAs });  // the handlers of this render
  latest.current = { play, save, saveAs };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target instanceof Element ? e.target : document.body;
      const typing = !!el.closest("input, textarea, [contenteditable]");
      if (el.closest(".dialog")) return;
      const mod = e.metaKey || e.ctrlKey;
      const k = e.key.toLowerCase();
      if (mod && k === "s") {
        e.preventDefault();
        void (e.shiftKey ? latest.current.saveAs() : latest.current.save());
      } else if (mod && k === "z" && !typing) {
        e.preventDefault();
        void (e.shiftKey ? client.redo() : client.undo());
      } else if (e.key === " " && !mod && !typing && !e.repeat) {
        e.preventDefault(); // also keeps a focused button from being clicked
        latest.current.play();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Closing the main window with unsaved values asks first.
  useEffect(() => {
    if (!bar) return;
    const f = (e: BeforeUnloadEvent) => { if (client.editedCount() > 0) e.preventDefault(); };
    window.addEventListener("beforeunload", f);
    return () => window.removeEventListener("beforeunload", f);
  }, [bar]);

  const dialogView = dialog !== null && w.speaker && (
    <SaveDialog t={t} speaker={w.speaker} initial={dialog} onClose={() => setDialog(null)}
      onDone={(path) => { setDialog(null); onNote(t("note.saved", { path })); }} />
  );
  if (!bar) return dialogView || null;

  const h = c.project?.history;
  const n = c.editedCount();
  const status = (n ? t("status.unsaved", { n }) : t("status.saved"))
    + (w.speaker ? " · " + t("status.speaker", { name: w.speaker }) : "");
  const playing = p.status !== "idle";
  return (
    <footer className="status">
      <button className="tbtn icon" onClick={play} disabled={!w.shape} aria-pressed={playing}
        title={playing ? t("stop") : t("play")} aria-label={playing ? t("stop") : t("play")}>{playing ? "■" : "▶"}</button>
      <span className="mono">{p.position.toFixed(3)} s</span>
      <button className="tbtn" disabled={!h?.can_undo} onClick={() => void c.undo()}
        title={h?.undo_label ? t("undo.what", { label: h.undo_label }) : undefined}>{t("undo")}</button>
      <button className="tbtn" disabled={!h?.can_redo} onClick={() => void c.redo()}
        title={h?.redo_label ? t("redo.what", { label: h.redo_label }) : undefined}>{t("redo")}</button>
      <button className="tbtn" disabled={!w.speaker} onClick={() => void save()} title={t("save")}>{t("save")}</button>
      <button className="tbtn long" disabled={!w.speaker} onClick={saveAs} title={t("save_as")}>{t("save_as")}</button>
      <span className="grow" />
      {c.status !== "open" ? (
        <span className={"mono clip" + (c.status === "closed" ? " err" : "")}>
          {t(c.status === "connecting" ? "status.connecting" : "status.disconnected")}
        </span>
      ) : (
        <span className="mono clip" title={status}>{status}</span>
      )}
      {dialogView}
    </footer>
  );
}
