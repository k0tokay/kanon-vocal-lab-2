// Lists of named things (vocal tract shapes, glottis shapes, glottis models)
// with a status mark per row (未整備 / 調整中 / 整備済み) and a row menu (▾ or
// right click): the status, and for shapes add / duplicate / rename / delete.
// Every change is an operation on the server, so it can be undone and saved.

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { T } from "../i18n";
import { LEVELS, client, useClient, type Address, type Level } from "../store";
import { Menu, type MenuItem } from "./Menu";

const GLYPH: Record<Level, string> = { todo: "□", wip: "▣", done: "■" };

export function statusItems(t: T, speaker: string, what: Address): MenuItem[] {
  const now = client.statusOf(speaker, what);
  return [
    { heading: t("level.title") },
    ...LEVELS.map((l) => ({
      label: `${GLYPH[l]} ${t("level." + l)}`, selected: l === now,
      onClick: () => { if (l !== now) void client.op("status.set", { speaker, what, level: l }); },
    })),
  ];
}

/** One row: ● (unsaved), the name, a tag, the status mark and ▾. */
export function Row({ t, name, sel, edited, disabled, title, tag, level, onSelect, menu }: {
  t: T; name: string; sel: boolean; edited: boolean; disabled?: boolean; title?: string; tag?: ReactNode;
  level: Level; onSelect: () => void; menu: (() => MenuItem[]) | null;
}) {
  const [at, setAt] = useState<{ x: number; y: number } | null>(null);
  return (
    <div className={"row srow" + (sel ? " sel" : "") + (edited ? " edited" : "") + (disabled ? " off" : "")}
      onContextMenu={(e) => { if (!menu) return; e.preventDefault(); setAt({ x: e.clientX, y: e.clientY }); }}>
      <button className="pick" disabled={disabled} aria-pressed={sel} title={title ?? name} onClick={onSelect}>
        <span className="mono mark">{edited ? "●" : ""}</span>
        <span className="name">{name}</span>
        {tag}
      </button>
      <span className={"mono st " + level} title={t("level." + level)} aria-label={t("level." + level)}>{GLYPH[level]}</span>
      {menu && (
        <button className="more mono" aria-haspopup="menu" title={t("shape.menu", { name })} aria-label={t("shape.menu", { name })}
          onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setAt({ x: r.left, y: r.bottom }); }}>▾</button>
      )}
      {at && menu && <Menu x={at.x} y={at.y} items={menu()} onClose={() => setAt(null)} />}
    </div>
  );
}

type Dialog =
  // `own`: the name the shape has now (renaming to it changes nothing)
  | { type: "name"; title: string; initial: string; ok: string; own?: string; run: (name: string) => Promise<unknown> }
  | { type: "confirm"; title: string; message: string; ok: string; run: () => Promise<unknown> };

/** The shapes of the vocal tract (kind "tract") or of one glottis model (kind "glottis"). */
export function ShapeList({ t, speaker, kind, model, names, selected, edited, onSelect }: {
  t: T; speaker: string; kind: "tract" | "glottis"; model?: string;
  names: string[]; selected: string | null; edited: Set<string>; onSelect: (name: string) => void;
}) {
  useClient();
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const base = { speaker, ...(kind === "glottis" && model ? { model } : {}) };
  const what = (n: string): Address => (kind === "tract" ? ["tract_shape", n] : ["glottis_shape", model!, n]);
  // run an operation; its error goes back to the dialog (e.g. a name that is taken)
  const op = (name: string, args: Record<string, unknown>) => client.request("op", { op: `${kind}.${name}`, args: { ...base, ...args } });

  const add = () => setDialog({
    type: "name", title: t("shape.add_title"), initial: freeName(t("shape.new_name"), names), ok: t("shape.add"),
    run: async (name) => { await op("add_shape", { name }); onSelect(name); },
  });
  const menu = (n: string) => (): MenuItem[] => [
    ...statusItems(t, speaker, what(n)),
    "sep",
    { label: t("shape.add") + "…", onClick: add },
    { label: t("shape.duplicate") + "…", onClick: () => setDialog({
      type: "name", title: t("shape.duplicate_title", { name: n }), initial: freeName(n + "-copy", names), ok: t("shape.duplicate"),
      run: async (name) => { await op("duplicate_shape", { shape: n, name }); onSelect(name); },
    }) },
    { label: t("shape.rename") + "…", onClick: () => setDialog({
      type: "name", title: t("shape.rename_title", { name: n }), initial: n, ok: t("shape.rename"), own: n,
      run: async (name) => { if (name === n) return; await op("rename_shape", { shape: n, name }); if (n === selected) onSelect(name); },
    }) },
    { label: t("shape.delete") + "…", disabled: names.length <= 1, onClick: () => setDialog({
      type: "confirm", title: t("shape.delete_title", { name: n }), message: t("shape.delete_note"), ok: t("shape.delete"),
      run: () => op("delete_shape", { shape: n }),
    }) },
  ];

  return (
    <div className="list">
      {names.map((n) => (
        <Row key={n} t={t} name={n} sel={n === selected} edited={edited.has(n)} level={client.statusOf(speaker, what(n))}
          onSelect={() => onSelect(n)} menu={menu(n)} />
      ))}
      <button className="row addrow" onClick={add}>
        <span className="mono mark">+</span><span className="name">{t("shape.add")}…</span>
      </button>
      {dialog && createPortal(
        dialog.type === "name"
          ? <NameDialog t={t} title={dialog.title} initial={dialog.initial} ok={dialog.ok}
              taken={(s) => s !== dialog.own && names.includes(s)}
              run={dialog.run} onClose={() => setDialog(null)} />
          : <ConfirmDialog t={t} title={dialog.title} message={dialog.message} ok={dialog.ok}
              run={dialog.run} onClose={() => setDialog(null)} />,
        document.body)}
    </div>
  );
}

function freeName(base: string, names: string[]) {
  if (!names.includes(base)) return base;
  for (let i = 2; ; i++) if (!names.includes(`${base}-${i}`)) return `${base}-${i}`;
}

/** Asks for a name. A name that is taken is refused here and by the server. */
function NameDialog({ t, title, initial, ok, taken, run, onClose }: {
  t: T; title: string; initial: string; ok: string; taken: (name: string) => boolean;
  run: (name: string) => Promise<unknown>; onClose: () => void;
}) {
  const [name, setName] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { input.current!.focus(); input.current!.select(); }, []);
  const n = name.trim();
  const clash = n !== "" && taken(n);
  const submit = async () => {
    if (!n || clash || busy) return;
    setBusy(true);
    try { await run(n); onClose(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="scrim" onPointerDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <form className="dialog" role="dialog" aria-modal="true" aria-label={title}
        onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}
        onSubmit={(e) => { e.preventDefault(); void submit(); }}>
        <h2 className="clip">{title}</h2>
        <label className="field">
          <span className="mono">{t("shape.name")}</span>
          <input ref={input} className="mono" value={name} spellCheck={false} maxLength={64}
            onChange={(e) => { setName(e.target.value); setError(null); }} />
        </label>
        {(clash || error) && <p className="msg err">{clash ? t("shape.taken", { name: n }) : t("note.error", { message: error! })}</p>}
        <div className="actions">
          <button type="button" className="tbtn" onClick={onClose}>{t("save.cancel")}</button>
          <button type="submit" className="tbtn primary" disabled={busy || !n || clash}>{ok}</button>
        </div>
      </form>
    </div>
  );
}

function ConfirmDialog({ t, title, message, ok, run, onClose }: {
  t: T; title: string; message: string; ok: string; run: () => Promise<unknown>; onClose: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const btn = useRef<HTMLButtonElement>(null);
  useEffect(() => { btn.current!.focus(); }, []);
  return (
    <div className="scrim" onPointerDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <form className="dialog" role="alertdialog" aria-modal="true" aria-label={title}
        onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}
        onSubmit={(e) => { e.preventDefault(); run().then(onClose, (x: Error) => setError(x.message)); }}>
        <h2 className="clip">{title}</h2>
        <p className="msg">{message}</p>
        {error && <p className="msg err">{t("note.error", { message: error })}</p>}
        <div className="actions">
          <button type="button" className="tbtn" onClick={onClose}>{t("save.cancel")}</button>
          <button ref={btn} type="submit" className="tbtn primary danger">{ok}</button>
        </div>
      </form>
    </div>
  );
}
