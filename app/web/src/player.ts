// Playing a held vowel: the server synthesizes it with VTL (and keeps the
// sounds it made), the browser plays the WAV. One sound at a time per window.
// Nothing here is project data: playing never enters the undo history.

import { useSyncExternalStore } from "react";

export type PlayStatus = "idle" | "loading" | "playing";

export interface SoundInfo { duration: number; rms: number; peak: number; sampleRate: number }

class Player {
  status: PlayStatus = "idle";
  /** seconds into the sound being played */
  position = 0;
  /** the last sound decoded (for checks from the console) */
  last: SoundInfo | null = null;
  version = 0;

  private ctx: AudioContext | null = null;
  private src: AudioBufferSourceNode | null = null;
  private started = 0;
  private raf = 0;
  private token = 0;
  private listeners = new Set<() => void>();

  subscribe = (f: () => void) => { this.listeners.add(f); return () => { this.listeners.delete(f); }; };
  private changed() { this.version++; this.listeners.forEach((f) => f()); }

  /** Synthesize `params` of `speaker` and play it. Throws (after resetting) on failure. */
  async play(speaker: string, params: number[], duration = 1.0, glottisShape?: string) {
    this.stop();
    const token = ++this.token;
    this.status = "loading";
    this.changed();
    // created on the click, so the browser allows sound
    const ctx = (this.ctx ??= new AudioContext());
    if (ctx.state === "suspended") await ctx.resume();
    try {
      const r = await fetch("/api/sustained", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ speaker, params, duration, ...(glottisShape ? { glottis_shape: glottisShape } : {}) }),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => null))?.error ?? `HTTP ${r.status}`);
      const buf = await ctx.decodeAudioData(await r.arrayBuffer());
      if (token !== this.token) return; // stopped or replaced meanwhile
      const x = buf.getChannelData(0);
      let s = 0, peak = 0;
      for (let i = 0; i < x.length; i++) { s += x[i] * x[i]; peak = Math.max(peak, Math.abs(x[i])); }
      this.last = { duration: buf.duration, rms: Math.sqrt(s / x.length), peak, sampleRate: buf.sampleRate };
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(ctx.destination);
      src.onended = () => { if (this.src === src) this.finish(); };
      this.src = src;
      this.started = ctx.currentTime;
      this.position = 0;
      this.status = "playing";
      src.start();
      const tick = () => {
        if (this.src !== src) return;
        this.position = Math.min(ctx.currentTime - this.started, buf.duration);
        this.changed();
        this.raf = requestAnimationFrame(tick);
      };
      this.raf = requestAnimationFrame(tick);
      this.changed();
    } catch (e) {
      if (token === this.token) this.finish();
      throw e;
    }
  }

  stop() {
    this.token++;
    const src = this.src;
    this.src = null;
    if (src) { try { src.stop(); } catch { /* already ended */ } }
    this.finish();
  }

  private finish() {
    cancelAnimationFrame(this.raf);
    this.src = null;
    if (this.status !== "idle" || this.position !== 0) {
      this.status = "idle";
      this.position = 0;
      this.changed();
    }
  }
}

export const player = new Player();
(window as unknown as { __player: Player }).__player = player;

export function usePlayer(): Player {
  useSyncExternalStore(player.subscribe, () => player.version);
  return player;
}
