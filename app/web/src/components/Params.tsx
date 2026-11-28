import { useRef, useState } from "react";
import type { T } from "../i18n";
import { client, type TractParamInfo } from "../store";

// Parameter groups of the vocal tract model (names are VTL's).
export const GROUPS: [string, string[]][] = [
  ["group.hyoid_jaw", ["HX", "HY", "JX", "JA"]],
  ["group.lips", ["LP", "LD"]],
  ["group.velum", ["VS", "VO"]],
  ["group.tongue_body", ["TCX", "TCY", "TBX", "TBY"]],
  ["group.tongue_tip", ["TTX", "TTY"]],
  ["group.tongue_root", ["TRX", "TRY"]],
  ["group.tongue_sides", ["TS1", "TS2", "TS3"]],
];

let dragCounter = 0;

function Slider({ label, min, max, value, onDrag, onDragEnd, onStep }: {
  label: string; min: number; max: number; value: number;
  onDrag: (v: number) => void; onDragEnd: (v: number) => void; onStep: (v: number) => void;
}) {
  const el = useRef<HTMLDivElement>(null);
  const span = max - min;
  const frac = Math.min(1, Math.max(0, (value - min) / span));
  const at = (clientX: number) => {
    const r = el.current!.getBoundingClientRect();
    return min + Math.min(1, Math.max(0, (clientX - r.left) / r.width)) * span;
  };
  return (
    <div
      ref={el} className="slider" role="slider" tabIndex={0}
      aria-label={label} aria-valuemin={min} aria-valuemax={max} aria-valuenow={value}
      onPointerDown={(e) => { el.current!.setPointerCapture(e.pointerId); onDrag(at(e.clientX)); }}
      onPointerMove={(e) => { if (el.current!.hasPointerCapture(e.pointerId)) onDrag(at(e.clientX)); }}
      onPointerUp={(e) => { if (el.current!.hasPointerCapture(e.pointerId)) onDragEnd(at(e.clientX)); }}
      onKeyDown={(e) => {
        const d = e.key === "ArrowRight" || e.key === "ArrowUp" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowDown" ? -1 : 0;
        if (d) { e.preventDefault(); onStep(value + d * span / (e.shiftKey ? 10 : 100)); }
      }}
    >
      <div className="fill" style={{ width: `${frac * 100}%` }} />
      <div className="knob" style={{ left: `calc(${frac} * (100% - 8px))` }} />
    </div>
  );
}

/** One editable number: a slider when it has a range, and the value, which can be typed.
 *  `op` with `args` (+ `value`) is the operation that sets it; a drag is one undo step. */
export function ValueRow({ label, title, min, max, value, edited, op, args, wide }: {
  label: string; title?: string; min: number; max: number; value: number; edited: boolean;
  op: string; args: Record<string, unknown>; wide?: boolean;
}) {
  // While dragging, show the pointer's value at once; the server's comes back a moment later.
  const [local, setLocal] = useState<number | null>(null);
  const [typing, setTyping] = useState<string | null>(null);
  const drag = useRef<{ id: string; frame: number; latest: number } | null>(null);
  const shown = local ?? value;
  const ranged = max > min;

  const send = (v: number, dragId?: string) => client.op(op, { ...args, value: v }, dragId);

  const onDrag = (v: number) => {
    setLocal(v);
    let d = drag.current;
    if (!d) d = drag.current = { id: `${op}/${label}/${++dragCounter}`, frame: 0, latest: v };
    d.latest = v;
    if (!d.frame) d.frame = requestAnimationFrame(() => { d!.frame = 0; void send(d!.latest, d!.id); });
  };
  const onDragEnd = (v: number) => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    if (d.frame) cancelAnimationFrame(d.frame);
    void send(v, d.id).then(() => client.endDrag(d.id)).finally(() => setLocal(null));
  };
  const commitTyping = () => {
    if (typing === null) return;
    const v = Number(typing.trim());
    setTyping(null);
    if (typing.trim() !== "" && Number.isFinite(v) && v !== value) void send(v);
  };

  return (
    <div className={"param" + (wide ? " wide" : "") + (edited ? " edited" : "")}>
      <span className="mono clip" title={title ?? label}>{label}</span>
      {ranged
        ? <Slider label={label} min={min} max={max} value={shown} onDrag={onDrag} onDragEnd={onDragEnd} onStep={(v) => void send(v)} />
        : <span />}
      {typing === null ? (
        <button className="v" title={shown.toFixed(4)} onClick={() => setTyping(value.toFixed(4))}>{shown.toFixed(3)}</button>
      ) : (
        <input
          className="v" autoFocus value={typing} aria-label={label}
          onChange={(e) => setTyping(e.target.value)}
          onFocus={(e) => e.target.select()}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitTyping();
            if (e.key === "Escape") setTyping(null);
          }}
          onBlur={commitTyping}
        />
      )}
    </div>
  );
}

function ParamRow({ speaker, shape, info, value }: {
  speaker: string; shape: string; info: TractParamInfo; value: number;
}) {
  return (
    <ValueRow label={info.name} min={info.min} max={info.max} value={value}
      edited={client.isEdited(speaker, ["tract_shape", shape, info.name])}
      op="tract.set_param" args={{ speaker, shape, param: info.name }} />
  );
}

export function Params({ speaker, shape, t }: { speaker: string; shape: string; t: T }) {
  const sp = client.project!.speakers[speaker];
  const values = sp.tract.shapes[shape];
  const byName = new Map(sp.tract.params.map((p) => [p.name, p]));
  const grouped = new Set(GROUPS.flatMap(([, ps]) => ps));
  const rest = sp.tract.params.map((p) => p.name).filter((n) => !grouped.has(n));
  const groups: [string, string[]][] = rest.length ? [...GROUPS, ["", rest]] : GROUPS;
  return (
    <div className="params">
      {groups.map(([g, names]) => (
        <div className="group" key={g}>
          {g && <h3>{t(g)}</h3>}
          {names.filter((n) => byName.has(n)).map((n) => {
            const info = byName.get(n)!;
            return <ParamRow key={n} speaker={speaker} shape={shape} info={info} value={values[info.index]} />;
          })}
        </div>
      ))}
    </div>
  );
}
