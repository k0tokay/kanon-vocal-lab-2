import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { EDITORS, editorKind, editorMin } from "../editors";
import type { T } from "../i18n";
import {
  DIVIDER, joinArea, leaves, minSize, neighbour, removeArea, resize, splitArea,
  type Leaf, type Node, type Side, type Split,
} from "../layout";

// ---------------------------------------------------------------------------
// What areas can do to the layout of their window

export interface LayoutActions {
  root: Node | null; // null in a detached window (one area, no layout)
  set: (root: Node) => void;
  reset: () => void;
  detach: (area: Leaf, rect: DOMRect) => void;
  setEditor: (area: Leaf, editor: string) => void;
}

const LayoutCtx = createContext<LayoutActions | null>(null);
export const LayoutProvider = LayoutCtx.Provider;
const useLayout = () => useContext(LayoutCtx)!;

// ---------------------------------------------------------------------------
// A floating menu (principles §5: frame and hard offset shadow)

export type MenuItem = { label: string; onClick: () => void; selected?: boolean } | "sep";

export function Menu({ x, y, items, onClose }: { x: number; y: number; items: MenuItem[]; onClose: () => void }) {
  const el = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ x, y });
  useEffect(() => {
    // keep the menu inside the window
    const r = el.current!.getBoundingClientRect();
    setPos({ x: Math.max(0, Math.min(x, innerWidth - r.width - 8)), y: Math.max(0, Math.min(y, innerHeight - r.height - 8)) });
    const down = (e: PointerEvent) => { if (!el.current!.contains(e.target as Element)) onClose(); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("pointerdown", down, true);
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener("pointerdown", down, true); window.removeEventListener("keydown", key); };
  }, [x, y, onClose]);
  return (
    <div className="menu" role="menu" ref={el} style={{ left: pos.x, top: pos.y }}>
      {items.map((it, i) => it === "sep" ? <div key={i} className="msep" /> : (
        <button key={i} role="menuitem" className={"row" + (it.selected ? " sel" : "")} title={it.label}
          onClick={() => { onClose(); it.onClick(); }}>
          <span className="name">{it.label}</span>
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// One area: header (editor name ▾, info) and the editor

export function AreaView({ area, t, onNote }: { area: Leaf; t: T; onNote: (s: string) => void }) {
  const L = useLayout();
  const kind = editorKind(area.editor);
  const box = useRef<HTMLElement>(null);
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);

  const items: MenuItem[] = EDITORS.map((e) => ({
    label: t("ed." + e.id), selected: e.id === area.editor, onClick: () => L.setEditor(area, e.id),
  }));
  if (L.root) {
    const root = L.root;
    items.push("sep",
      { label: t("menu.split_row"), onClick: () => L.set(splitArea(root, area.id, "row")) },
      { label: t("menu.split_column"), onClick: () => L.set(splitArea(root, area.id, "column")) });
    for (const side of ["before", "after"] as Side[]) {
      const nb = neighbour(root, area.id, side);
      if (!nb) continue;
      const where = nb.dir === "row" ? (side === "before" ? "left" : "right") : (side === "before" ? "above" : "below");
      items.push({ label: t("menu.join." + where, { editor: t("ed." + nb.leaf.editor) }), onClick: () => L.set(joinArea(root, area.id, side)) });
    }
    if (leaves(root).length > 1) items.push({ label: t("menu.close"), onClick: () => L.set(removeArea(root, area.id)) });
    items.push("sep",
      { label: t("menu.detach"), onClick: () => L.detach(area, box.current!.getBoundingClientRect()) },
      { label: t("menu.reset"), onClick: () => { L.reset(); onNote(t("note.layout_reset")); } });
  }

  const open = (x: number, y: number) => setMenu({ x, y });
  return (
    <section className="area" ref={box} data-editor={area.editor}>
      <div className="ahead" onContextMenu={(e) => { e.preventDefault(); open(e.clientX, e.clientY); }}>
        <button className="etype" title={t("ed." + area.editor)} aria-haspopup="menu"
          onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); open(r.left, r.bottom); }}>
          {t("ed." + area.editor)}
        </button>
        <span className="grow" />
        {kind.Info && <kind.Info t={t} />}
      </div>
      <kind.Body t={t} />
      {menu && <Menu x={menu.x} y={menu.y} items={items} onClose={() => setMenu(null)} />}
    </section>
  );
}

// ---------------------------------------------------------------------------
// The tree: splits are CSS grids, children separated by draggable dividers

function Divider({ split, index, container }: { split: Split; index: number; container: () => HTMLElement }) {
  const L = useLayout();
  const drag = useRef<{ start: number; px: number[]; avail: number } | null>(null);
  const row = split.dir === "row";
  const mins = split.children.map((c) => { const m = minSize(c, editorMin); return row ? m.w : m.h; });
  return (
    <div
      className={"divider dv-" + split.dir} role="separator" aria-orientation={row ? "vertical" : "horizontal"}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        // start from the sizes on screen (a track held at its minimum differs from its share)
        const kids = [...container().children].filter((k) => !k.classList.contains("divider"));
        const px = kids.map((k) => { const r = k.getBoundingClientRect(); return row ? r.width : r.height; });
        const avail = px.reduce((a, b) => a + b, 0);
        drag.current = { start: row ? e.clientX : e.clientY, px, avail };
      }}
      onPointerMove={(e) => {
        const d = drag.current;
        if (!d || !e.currentTarget.hasPointerCapture(e.pointerId)) return;
        const pair = d.px[index] + d.px[index + 1];
        // both neighbours keep at least their minimum size
        let a = d.px[index] + ((row ? e.clientX : e.clientY) - d.start);
        a = Math.max(mins[index], Math.min(pair - mins[index + 1], a));
        if (pair < mins[index] + mins[index + 1]) return;
        const px = [...d.px];
        px[index] = a;
        px[index + 1] = pair - a;
        L.set(resize(L.root!, split.id, px.map((p) => p / d.avail)));
      }}
      onPointerUp={() => { drag.current = null; }}
    />
  );
}

function SplitView({ split, t, onNote }: { split: Split; t: T; onNote: (s: string) => void }) {
  const el = useRef<HTMLDivElement>(null);
  const row = split.dir === "row";
  const tracks: string[] = [];
  const parts: ReactNode[] = [];
  split.children.forEach((c, i) => {
    const m = minSize(c, editorMin);
    // factors x100: CSS grid counts a flex sum below 1 as 1, which would leave space unused
    // once some tracks are held at their minimum
    tracks.push(`minmax(${row ? m.w : m.h}px, ${(split.sizes[i] * 100).toFixed(3)}fr)`);
    parts.push(<NodeView key={c.id} node={c} t={t} onNote={onNote} />);
    if (i < split.children.length - 1) {
      tracks.push(`${DIVIDER}px`);
      parts.push(<Divider key={c.id + "/d"} split={split} index={i} container={() => el.current!} />);
    }
  });
  const style = row
    ? { gridTemplateColumns: tracks.join(" "), gridTemplateRows: "minmax(0, 1fr)" }
    : { gridTemplateRows: tracks.join(" "), gridTemplateColumns: "minmax(0, 1fr)" };
  return <div className="split" ref={el} style={style}>{parts}</div>;
}

export function NodeView({ node, t, onNote }: { node: Node; t: T; onNote: (s: string) => void }) {
  return node.type === "area"
    ? <AreaView area={node} t={t} onNote={onNote} />
    : <SplitView split={node} t={t} onNote={onNote} />;
}

