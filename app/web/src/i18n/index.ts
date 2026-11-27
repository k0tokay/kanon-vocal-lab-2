// Every user-visible string lives in a JSON file in this folder, one per
// language. Adding a language is adding a file (e.g. `kono.json`) with the
// same keys plus "_name" (shown in the switcher) and "_order".

import { useSyncExternalStore } from "react";

type Dict = Record<string, string | number>;

const files = import.meta.glob<Dict>("./*.json", { eager: true, import: "default" });

export const LOCALES: { code: string; name: string; dict: Dict }[] = Object.entries(files)
  .map(([path, dict]) => ({ code: path.replace(/^\.\/|\.json$/g, ""), name: String(dict._name), dict }))
  .sort((a, b) => Number(a.dict._order ?? 99) - Number(b.dict._order ?? 99) || a.code.localeCompare(b.code));

const DEFAULT = "en";
const KEY = "ui.lang";

function load(): string {
  try {
    const v = localStorage.getItem(KEY);
    if (v && LOCALES.some((l) => l.code === v)) return v;
  } catch { /* storage may be unavailable */ }
  return DEFAULT;
}

let current = load();
const listeners = new Set<() => void>();

export function setLang(code: string) {
  current = code;
  try { localStorage.setItem(KEY, code); } catch { /* ignore */ }
  document.documentElement.lang = code;
  listeners.forEach((f) => f());
}

export type T = (key: string, vars?: Record<string, string | number>) => string;

function translate(code: string): T {
  const dict = LOCALES.find((l) => l.code === code)?.dict ?? {};
  const fallback = LOCALES.find((l) => l.code === DEFAULT)?.dict ?? {};
  return (key, vars) => {
    let s = String(dict[key] ?? fallback[key] ?? key);
    for (const [k, v] of Object.entries(vars ?? {})) s = s.replaceAll(`{${k}}`, String(v));
    return s;
  };
}

/** The current language and its translate function; re-renders on change. */
export function useT(): [T, string] {
  const code = useSyncExternalStore(
    (f) => { listeners.add(f); return () => listeners.delete(f); },
    () => current,
  );
  return [translate(code), code];
}

document.documentElement.lang = current;
