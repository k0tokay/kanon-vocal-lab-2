// The screen's copy of the server's data. The server holds the data; this
// file only mirrors it: it applies the change events the server broadcasts
// and sends requests (operations, undo, computations) over the WebSocket.

import { useSyncExternalStore } from "react";

export type Address = (string | number)[];

export interface TractParamInfo { index: number; name: string; min: number; max: number; neutral: number }
export interface GlottisModel { type: string; selected: boolean; shapes: Record<string, number[]> }
export interface Speaker {
  path: string | null;
  tract: { params: TractParamInfo[]; shapes: Record<string, number[]> };
  glottis: { selected: string; models: GlottisModel[] };
  modified: boolean;
  edited: { address: Address; saved: unknown }[];
}
export interface HistoryState {
  can_undo: boolean; can_redo: boolean; undo_label: string | null; redo_label: string | null; open: string | null;
}
export interface Project { speakers: Record<string, Speaker>; history: HistoryState }

interface Change { speaker: string; address: Address; value: unknown; edited: boolean; saved: unknown }

type Status = "connecting" | "open" | "closed";

const key = (speaker: string, address: Address) => speaker + "\u0000" + JSON.stringify(address);

class Client {
  project: Project | null = null;
  app = "";
  status: Status = "connecting";
  /** speaker+address -> value at the last save, for values that differ from it */
  edited = new Map<string, unknown>();
  version = 0;
  errors = new Set<(message: string) => void>();

  private ws: WebSocket | null = null;
  private nextId = 1;
  private pending = new Map<number, { resolve: (v: any) => void; reject: (e: Error) => void }>();
  private listeners = new Set<() => void>();

  connect() {
    const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
    this.ws = ws;
    ws.onopen = () => this.setStatus("open");
    ws.onmessage = (m) => this.receive(JSON.parse(m.data));
    ws.onclose = () => {
      this.setStatus("closed");
      for (const p of this.pending.values()) p.reject(new Error("connection closed"));
      this.pending.clear();
      setTimeout(() => this.connect(), 1000);
    };
  }

  private setStatus(s: Status) { this.status = s; this.changed(); }

  private changed() {
    this.version++;
    this.listeners.forEach((f) => f());
  }

  subscribe = (f: () => void) => { this.listeners.add(f); return () => { this.listeners.delete(f); }; };

  private receive(msg: any) {
    if (msg.type === "reply") {
      const p = this.pending.get(msg.id);
      this.pending.delete(msg.id);
      if (!p) return;
      if ("error" in msg) p.reject(new Error(msg.error));
      else p.resolve(msg.result);
      return;
    }
    if (msg.type === "hello") {
      this.app = msg.app;
      this.setProject(msg.project);
      return;
    }
    if (msg.history && this.project) this.project.history = msg.history;
    if (msg.type === "changed") {
      let needFull = false;
      for (const c of msg.changes as Change[]) needFull = !this.apply(c) || needFull;
      if (needFull) { void this.refresh(); return; }
    } else if (msg.type === "speaker_saved" || msg.type === "speaker_opened") {
      void this.refresh();
      return;
    }
    this.changed();
  }

  private setProject(p: Project) {
    this.project = p;
    this.edited.clear();
    for (const [sid, sp] of Object.entries(p.speakers))
      for (const e of sp.edited) this.edited.set(key(sid, e.address), e.saved);
    this.changed();
  }

  async refresh() { this.setProject(await this.request("project")); }

  /** Apply one change in place. False if this kind of address needs a full reload. */
  private apply(c: Change): boolean {
    const sp = this.project?.speakers[c.speaker];
    if (!sp) return false;
    const k = key(c.speaker, c.address);
    if (c.edited) this.edited.set(k, c.saved); else this.edited.delete(k);
    const [kind] = c.address;
    if (kind === "tract_shape") {
      const [, shape, param] = c.address;
      const i = sp.tract.params.findIndex((p) => p.name === param);
      const values = sp.tract.shapes[shape as string];
      if (i < 0 || !values) return false;
      values[i] = c.value as number;
      return true;
    }
    if (kind === "glottis_shape") {
      const [, model, shape, index] = c.address;
      const values = sp.glottis.models.find((m) => m.type === model)?.shapes[shape as string];
      if (!values) return false;
      values[index as number] = c.value as number;
      return true;
    }
    return false;
  }

  isEdited(speaker: string, address: Address) { return this.edited.has(key(speaker, address)); }
  savedValue(speaker: string, address: Address) { return this.edited.get(key(speaker, address)); }
  editedCount() { return this.edited.size; }
  editedAddresses(speaker: string): Address[] {
    const p = speaker + "\u0000";
    return [...this.edited.keys()].filter((k) => k.startsWith(p)).map((k) => JSON.parse(k.slice(p.length)));
  }

  request<R = any>(kind: string, payload: Record<string, unknown> = {}): Promise<R> {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) return Promise.reject(new Error("not connected"));
    const id = this.nextId++;
    return new Promise<R>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, kind, ...payload }));
    });
  }

  /** Run an operation; errors are reported to `errors` listeners. */
  op(op: string, args: Record<string, unknown>, drag?: string) {
    return this.request("op", { op, args, ...(drag ? { drag } : {}) }).catch((e) => this.report(e));
  }
  endDrag(drag: string) { return this.request("drag_end", { drag }).catch((e) => this.report(e)); }
  undo() { return this.request("undo").catch((e) => this.report(e)); }
  redo() { return this.request("redo").catch((e) => this.report(e)); }

  report(e: Error) { this.errors.forEach((f) => f(e.message)); }
}

export const client = new Client();
client.connect();

/** Re-render on every change of the mirrored data. */
export function useClient(): Client {
  useSyncExternalStore(client.subscribe, () => client.version);
  return client;
}
