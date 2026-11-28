// The areas of a workspace as a tree of plain JSON (Blender-like): a leaf
// shows one editor, a split lays its children out in a row (side by side)
// or a column (one above another) with relative sizes.
//
// The layout is view state: it is kept per workspace in localStorage and
// never enters the undo history. All functions here are pure; they return a
// new tree.

export interface Leaf { type: "area"; id: string; editor: string }
export interface Split { type: "split"; id: string; dir: "row" | "column"; sizes: number[]; children: Node[] }
export type Node = Leaf | Split;

export const DIVIDER = 2; // px, the thick rule between areas

let counter = 0;
export const newId = () => `a${Date.now().toString(36)}${(counter++).toString(36)}`;

const leaf = (editor: string): Leaf => ({ type: "area", id: newId(), editor });
const split = (dir: Split["dir"], sizes: number[], children: Node[]): Split =>
  ({ type: "split", id: newId(), dir, sizes, children });

/** The initial layout of each workspace. */
export function defaultLayout(workspace: string): Node {
  switch (workspace) {
    case "glottis":
      return split("row", [0.62, 0.38], [
        split("column", [0.56, 0.44], [leaf("gwave"), split("row", [0.55, 0.45], [leaf("gmodels"), leaf("gshapes")])]),
        split("column", [0.45, 0.55], [leaf("gparams"), leaf("gstatic")]),
      ]);
    case "tract":
    default:
      return split("row", [0.72, 0.28], [
        split("column", [0.68, 0.32], [leaf("tract"), split("row", [0.5, 0.5], [leaf("area"), leaf("spectrum")])]),
        split("column", [0.3, 0.7], [leaf("shapes"), leaf("params")]),
      ]);
  }
}

// ---------------------------------------------------------------------------
// Queries

export function findParent(root: Node, id: string): { parent: Split; index: number } | null {
  if (root.type !== "split") return null;
  const i = root.children.findIndex((c) => c.id === id);
  if (i >= 0) return { parent: root, index: i };
  for (const c of root.children) {
    const r = findParent(c, id);
    if (r) return r;
  }
  return null;
}

export function leaves(root: Node): Leaf[] {
  return root.type === "area" ? [root] : root.children.flatMap(leaves);
}

/** Smallest size in px a subtree can take, from the editors' minimum sizes. */
export function minSize(n: Node, editorMin: (editor: string) => { w: number; h: number }): { w: number; h: number } {
  if (n.type === "area") return editorMin(n.editor);
  const ms = n.children.map((c) => minSize(c, editorMin));
  const gaps = DIVIDER * (n.children.length - 1);
  return n.dir === "row"
    ? { w: ms.reduce((s, m) => s + m.w, 0) + gaps, h: Math.max(...ms.map((m) => m.h)) }
    : { w: Math.max(...ms.map((m) => m.w)), h: ms.reduce((s, m) => s + m.h, 0) + gaps };
}

// ---------------------------------------------------------------------------
// Edits (each returns a new tree)

function mapNode(root: Node, id: string, f: (n: Node) => Node): Node {
  if (root.id === id) return f(root);
  if (root.type === "area") return root;
  return { ...root, children: root.children.map((c) => mapNode(c, id, f)) };
}

/** Collapse splits with one child and splits inside splits of the same direction. */
export function normalize(n: Node): Node {
  if (n.type === "area") return n;
  const children: Node[] = [];
  let sizes: number[] = [];
  n.children.map(normalize).forEach((c, i) => {
    if (c.type === "split" && c.dir === n.dir) {
      children.push(...c.children);
      sizes.push(...c.sizes.map((s) => s * n.sizes[i]));
    } else {
      children.push(c);
      sizes.push(n.sizes[i]);
    }
  });
  if (children.length === 1) return children[0];
  const total = sizes.reduce((a, b) => a + b, 0);
  sizes = sizes.map((s) => s / total);
  return { ...n, children, sizes };
}

export function setEditor(root: Node, id: string, editor: string): Node {
  return mapNode(root, id, (n) => (n.type === "area" ? { ...n, editor } : n));
}

/** Split an area in two: "row" puts the new one to the right, "column" below. */
export function splitArea(root: Node, id: string, dir: Split["dir"]): Node {
  return normalize(mapNode(root, id, (n) => split(dir, [0.5, 0.5], [n, leaf((n as Leaf).editor)])));
}

export type Side = "before" | "after";

/** The leaf next to an area within its split, if any (only leaves can be joined). */
export function neighbour(root: Node, id: string, side: Side): { leaf: Leaf; dir: Split["dir"] } | null {
  const p = findParent(root, id);
  if (!p) return null;
  const j = p.index + (side === "after" ? 1 : -1);
  const n = p.parent.children[j];
  return n && n.type === "area" ? { leaf: n, dir: p.parent.dir } : null;
}

/** Join an area with its neighbour: the neighbour goes and the area takes its space. */
export function joinArea(root: Node, id: string, side: Side): Node {
  const p = findParent(root, id);
  const nb = neighbour(root, id, side);
  if (!p || !nb) return root;
  const j = p.index + (side === "after" ? 1 : -1);
  return normalize(mapNode(root, p.parent.id, (n) => {
    const s = n as Split;
    const sizes = [...s.sizes];
    sizes[p.index] += sizes[j];
    return { ...s, sizes: sizes.filter((_, k) => k !== j), children: s.children.filter((_, k) => k !== j) };
  }));
}

/** Remove an area (its space goes to its neighbours). The last area stays. */
export function removeArea(root: Node, id: string): Node {
  const p = findParent(root, id);
  if (!p) return root;
  return normalize(mapNode(root, p.parent.id, (n) => {
    const s = n as Split;
    return {
      ...s,
      sizes: s.sizes.filter((_, k) => k !== p.index),
      children: s.children.filter((_, k) => k !== p.index),
    };
  }));
}

/** Set the sizes of a split (after dragging a divider). */
export function resize(root: Node, splitId: string, sizes: number[]): Node {
  return mapNode(root, splitId, (n) => ({ ...(n as Split), sizes }));
}

// ---------------------------------------------------------------------------
// Keeping it per workspace

const KEY = (workspace: string) => `ui.layout.${workspace}`;
const VERSION = 1;

function valid(n: unknown, editors: Set<string>): n is Node {
  const x = n as Node;
  if (!x || typeof x.id !== "string") return false;
  if (x.type === "area") return editors.has(x.editor);
  return x.type === "split" && (x.dir === "row" || x.dir === "column") && Array.isArray(x.children)
    && x.children.length >= 2 && Array.isArray(x.sizes) && x.sizes.length === x.children.length
    && x.sizes.every((s) => typeof s === "number" && s > 0) && x.children.every((c) => valid(c, editors));
}

export function loadLayout(workspace: string, editors: Set<string>): Node {
  try {
    const raw = localStorage.getItem(KEY(workspace));
    if (raw) {
      const v = JSON.parse(raw);
      if (v.version === VERSION && valid(v.root, editors)) return v.root;
    }
  } catch { /* storage unavailable or broken: use the default */ }
  return defaultLayout(workspace);
}

export function saveLayout(workspace: string, root: Node) {
  try { localStorage.setItem(KEY(workspace), JSON.stringify({ version: VERSION, root })); } catch { /* ignore */ }
}
