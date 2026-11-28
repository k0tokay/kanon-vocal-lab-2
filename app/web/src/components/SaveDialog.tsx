import { useEffect, useRef, useState } from "react";
import type { T } from "../i18n";
import { client, type SaveResult } from "../store";

/** A file name to offer for "save as": the next version of a versioned speaker,
 *  else the same name with "-copy". */
export function suggestName(path: string | null, speaker: string): string {
  const name = path ? path.split(/[\\/]/).pop()! : speaker + ".speaker";
  const v = name.match(/^(.*-v\d+-\d+-)(\d+)\.speaker$/);
  if (v) return `${v[1]}${Number(v[2]) + 1}.speaker`;
  return name.replace(/\.speaker$/, "") + "-copy.speaker";
}

export function refusalNote(t: T, r: SaveResult & { ok: false }) {
  return t(r.reason === "versioned" ? "note.save_versioned" : "note.save_protected", { path: r.path });
}

/** "Save as": a path, and a second step to confirm overwriting a file that exists.
 *  Modal (principles §5: frame and hard offset shadow). */
export function SaveDialog({ t, speaker, initial, onDone, onClose }: {
  t: T; speaker: string; initial: string; onDone: (path: string) => void; onClose: () => void;
}) {
  const [path, setPath] = useState(initial);
  const [problem, setProblem] = useState<SaveResult | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const el = input.current!;
    el.focus();
    el.setSelectionRange(0, el.value.replace(/\.speaker$/, "").length);
  }, []);

  const submit = async (overwrite: boolean) => {
    setBusy(true);
    try {
      const r = await client.save(speaker, path.trim(), overwrite);
      if (r.ok) onDone(r.path); else setProblem(r);
    } catch (e) {
      client.report(e as Error);
    } finally {
      setBusy(false);
    }
  };
  const exists = problem && !problem.ok && problem.reason === "exists";

  return (
    <div className="scrim" onPointerDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <form className="dialog" role="dialog" aria-modal="true" aria-label={t("save.title", { speaker })}
        onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}
        onSubmit={(e) => { e.preventDefault(); if (!busy) void submit(!!exists); }}>
        <h2 className="clip">{t("save.title", { speaker })}</h2>
        <label className="field">
          <span className="mono">{t("save.path")}</span>
          <input ref={input} className="mono" value={path} spellCheck={false}
            onChange={(e) => { setPath(e.target.value); setProblem(null); }} />
        </label>
        {problem && !problem.ok && (
          <p className={"msg" + (exists ? "" : " err")}>
            {exists ? t("save.exists", { path: problem.path }) : refusalNote(t, problem)}
          </p>
        )}
        <div className="actions">
          <button type="button" className="tbtn" onClick={onClose}>{t("save.cancel")}</button>
          <button type="submit" className="tbtn primary" disabled={busy || !path.trim()}>
            {exists ? t("save.overwrite") : t("save.ok")}
          </button>
        </div>
      </form>
    </div>
  );
}
