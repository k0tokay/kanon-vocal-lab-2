import { useCallback, useEffect, useState, type ReactNode } from "react";
import { EDITOR_IDS } from "./editors";
import { LOCALES, setLang, useT, type T } from "./i18n";
import { defaultLayout, leaves, loadLayout, newId, removeArea, saveLayout, setEditor, type Leaf, type Node } from "./layout";
import { client, useClient } from "./store";
import { WorkspaceProvider, useWorkspace } from "./workspace";
import { AreaView, LayoutProvider, NodeView } from "./components/Areas";

const WORKSPACES = ["tract", "glottis", "articulation", "speak", "sing", "compare"];

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

function useKeys() {
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
}

// ---------------------------------------------------------------------------

export function App() {
  const c = useClient();
  const [t, lang] = useT();
  const [theme, setTheme] = useTheme();
  const [note, show] = useNote();
  useKeys();

  useEffect(() => {
    const f = (m: string) => show(t("note.error", { message: m }), true);
    c.errors.add(f);
    return () => { c.errors.delete(f); };
  }, [c, t, show]);

  const noteView = note && <div className={"note" + (note.error ? " err" : "")} role="status">{note.text}</div>;

  if (DETACHED) return <Detached t={t} editor={DETACHED} onNote={show} note={noteView} />;

  return (
    <WorkspaceProvider>
      <div className="app-grid">
        <header className="top">
          <span className="app" title={c.app}>{c.app || " "}</span>
          <nav className="tabs">
            {WORKSPACES.map((w) => (
              <button key={w} className="tab" aria-selected={w === WORKSPACE}
                title={t("ws." + w)} onClick={() => { if (w !== WORKSPACE) show(t("note.not_yet", { what: t("ws." + w) })); }}>
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
        <Layout workspace={WORKSPACE} t={t} onNote={show} />
        <StatusBar t={t} onPlay={() => show(t("note.not_yet", { what: t("note.play") }))} />
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

function Detached({ t, editor, onNote, note }: { t: T; editor: string; onNote: (s: string) => void; note: ReactNode }) {
  const [area, setArea] = useState<Leaf>({ type: "area", id: "detached", editor: EDITOR_IDS.has(editor) ? editor : "tract" });
  useEffect(() => { document.title = t("ed." + area.editor); }, [t, area.editor]);
  const actions = {
    root: null,
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
      </LayoutProvider>
      {note}
    </WorkspaceProvider>
  );
}

function StatusBar({ t, onPlay }: { t: T; onPlay: () => void }) {
  const c = useClient();
  const w = useWorkspace();
  const h = c.project?.history;
  const n = c.editedCount();
  const status = (n ? t("status.unsaved", { n }) : t("status.saved"))
    + (w.speaker ? " · " + t("status.speaker", { name: w.speaker }) : "");
  return (
    <footer className="status">
      <button className="tbtn" onClick={onPlay} title={t("play")} aria-label={t("play")}>▶</button>
      <span className="mono">0.000 s</span>
      <button className="tbtn" disabled={!h?.can_undo} onClick={() => void c.undo()}
        title={h?.undo_label ? t("undo.what", { label: h.undo_label }) : undefined}>{t("undo")}</button>
      <button className="tbtn" disabled={!h?.can_redo} onClick={() => void c.redo()}
        title={h?.redo_label ? t("redo.what", { label: h.redo_label }) : undefined}>{t("redo")}</button>
      <span className="grow" />
      {c.status !== "open" ? (
        <span className={"mono clip" + (c.status === "closed" ? " err" : "")}>
          {t(c.status === "connecting" ? "status.connecting" : "status.disconnected")}
        </span>
      ) : (
        <span className="mono clip" title={status}>{status}</span>
      )}
    </footer>
  );
}
