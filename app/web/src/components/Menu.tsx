import { useEffect, useRef, useState } from "react";

// ---------------------------------------------------------------------------
// A floating menu (principles §5: frame and hard offset shadow)

export type MenuItem =
  | { label: string; onClick: () => void; selected?: boolean; disabled?: boolean }
  | { heading: string }
  | "sep";

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
      {items.map((it, i) => it === "sep" ? <div key={i} className="msep" />
        : "heading" in it ? <div key={i} className="mhead mono clip" role="presentation">{it.heading}</div> : (
        <button key={i} role="menuitem" className={"row" + (it.selected ? " sel" : "")} title={it.label}
          disabled={it.disabled} onClick={() => { onClose(); it.onClick(); }}>
          <span className="name">{it.label}</span>
        </button>
      ))}
    </div>
  );
}
