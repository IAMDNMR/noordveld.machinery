import { clamp01, lerp, seg } from '../../lib/math'
import { filmData as D } from './launchData'

/*
  The launch film is a pure function of time `t` (seconds). One world, 1600 × 900, shared by every act, so elements
  can carry over from one act into the next. Layout constants live here so the cursor choreography and the scenes agree.
*/

export const WORLD_W = 1600
export const WORLD_H = 900
/** The story's own timeline (acts below) runs 0–48 s. The opening hook plays before it. */
export const STORY = 48
/** Opening hook: the stopped machine, before "I need something." */
export const HOOK = 3
/** Total film length as the viewer sees it */
export const DURATION = STORY + HOOK

/** Act start times. Previous / Next jump between these. */
export const ACTS = [
  { id: 'need', name: 'The need', start: 0 },
  { id: 'understand', name: 'Understanding', start: 3.6 },
  { id: 'machine', name: 'Machine', start: 8.2 },
  { id: 'part', name: 'Part intelligence', start: 12.6 },
  { id: 'sourcing', name: 'Sourcing', start: 18 },
  { id: 'fulfilment', name: 'Fulfilment', start: 23 },
  { id: 'agentic', name: 'Agentic', start: 29 },
  { id: 'transaction', name: 'Transaction', start: 33.5 },
  { id: 'service', name: 'Service', start: 37.5 },
  { id: 'reveal', name: 'Agentic Commerce', start: 41.5 },
] as const

/** Chapters in viewer time, for Previous / Next and the progress ticks */
export const CHAPTERS: readonly { id: string; name: string; start: number }[] = [{ id: 'hook', name: 'Machine down', start: 0 }, ...ACTS.map((a) => ({ ...a, start: a.start + HOOK }))]

/** The frame shown for reduced motion and before the film has started: the finished reveal. */
export const POSTER_TIME = 46.4 + HOOK

/** The customer's request, built from the film's graph records (machine model and part type). */
export const QUERY = `My ${D.machine.model} is down. I need a ${(D.part.subcategory || D.part.name).toLowerCase()}.`

/** Every key coordinate used by both the scenes and the cursor. */
export const P = {
  field0: { x: 550, y: 470, w: 500, h: 72 },
  field1: { x: 350, y: 150, w: 900, h: 76 },
  button: { x: 1190, y: 188 },
  chipY: 330,
  chipW: 330,
  chipH: 96,
  chipX: (i: number) => 110 + i * 350,
  card: { x: 140, y: 120, w: 1320, h: 660 },
  tilesX: [880, 1170] as const,
  tilesY: [320, 450, 580] as const,
  tile: { w: 270, h: 110 },
  partsTile: { x: 1015, y: 375 },
  listCard: { y: 200, w: 340, h: 170, x: (i: number) => 360 + i * 370 },
  detail: { x: 360, y: 90, w: 880, h: 420 },
  chainY: 655,
  chainX: (i: number) => 200 + i * 300,
  panel: { x: 100, y: 80, w: 1400, h: 740 },
  map: { x: 560, y: 110, w: 900, h: 680 },
  tabs: { y: 115, h: 44, sourcing: { x: 140, w: 130 }, fulfilment: { x: 280, w: 150 } },
  opt: { x: 130, w: 390, h: 118, y: (i: number) => 196 + i * 130 },
  pipeY: 430,
  pipeX: (i: number) => 170 + i * 252,
  checkout: { x: 500, y: 110, w: 600, h: 650 },
  cont: { x: 560, y: 620, w: 480, h: 72 },
  svcY: 300,
  svcX: (i: number) => 220 + i * 290,
}

/* ───────── Cursor choreography ───────── */

interface Way {
  t: number
  x: number
  y: number
}

/** Each waypoint is a stop: the cursor eases out of the previous one and settles into this one. */
const WAYS: readonly Way[] = [
  { t: 0.9, x: 1500, y: 860 },
  { t: 3.1, x: 900, y: 510 },
  { t: 3.5, x: 900, y: 510 },
  { t: 4.7, x: 930, y: 300 },
  { t: 6.2, x: 940, y: 296 },
  { t: 6.95, x: P.button.x + 6, y: P.button.y + 4 },
  { t: 7.6, x: P.button.x + 6, y: P.button.y + 4 },
  { t: 8.6, x: P.chipX(0) + 160, y: P.chipY + 62 },
  { t: 9.6, x: 700, y: 640 },
  { t: 10.9, x: P.partsTile.x + 40, y: P.partsTile.y + 14 },
  { t: 11.7, x: P.partsTile.x + 40, y: P.partsTile.y + 14 },
  { t: 14.2, x: P.listCard.x(0) + 190, y: P.listCard.y + 96 },
  { t: 14.85, x: P.listCard.x(0) + 190, y: P.listCard.y + 96 },
  { t: 17.4, x: 1330, y: 480 },
  { t: 19.2, x: 1300, y: 560 },
  { t: 22.2, x: P.tabs.fulfilment.x + 70, y: P.tabs.y + 26 },
  { t: 24.1, x: P.tabs.fulfilment.x + 70, y: P.tabs.y + 26 },
  { t: 25.1, x: P.opt.x + 230, y: P.opt.y(0) + 46 },
  { t: 25.65, x: P.opt.x + 230, y: P.opt.y(0) + 46 },
  { t: 29.8, x: 760, y: 520 },
  { t: 35.2, x: 1220, y: 520 },
  { t: 36.35, x: P.cont.x + 330, y: P.cont.y + 38 },
  { t: 37.2, x: P.cont.x + 330, y: P.cont.y + 38 },
]

/** The instants the cursor presses. The UI reacts at these times, and the ripple and sound follow them. */
export const CLICKS: readonly { t: number; x: number; y: number }[] = [
  { t: 3.3, x: 900, y: 510 },
  { t: 7.1, x: P.button.x + 6, y: P.button.y + 4 },
  { t: 8.75, x: P.chipX(0) + 160, y: P.chipY + 62 },
  { t: 11.75, x: P.partsTile.x + 40, y: P.partsTile.y + 14 },
  { t: 14.9, x: P.listCard.x(0) + 190, y: P.listCard.y + 96 },
  { t: 24.2, x: P.tabs.fulfilment.x + 70, y: P.tabs.y + 26 },
  { t: 25.7, x: P.opt.x + 230, y: P.opt.y(0) + 46 },
  { t: 36.4, x: P.cont.x + 330, y: P.cont.y + 38 },
]

const smooth = (u: number): number => u * u * u * (u * (u * 6 - 15) + 10)

export interface CursorState {
  x: number
  y: number
  opacity: number
  /** 1 at rest, dips on a press */
  press: number
}

export const cursorAt = (t: number): CursorState => {
  let x = WAYS[0].x
  let y = WAYS[0].y
  for (let i = 1; i < WAYS.length; i++) {
    const a = WAYS[i - 1]
    const b = WAYS[i]
    if (t < a.t) break
    const u = smooth(clamp01((t - a.t) / (b.t - a.t)))
    const dx = b.x - a.x
    const dy = b.y - a.y
    const dist = Math.hypot(dx, dy)
    // A hand does not move in a straight line: a slight arc, strongest mid-move
    const arc = dist > 1 ? Math.sin(Math.PI * u) * Math.min(46, dist * 0.07) : 0
    x = lerp(a.x, b.x, u) + (dist > 1 ? (-dy / dist) * arc : 0)
    y = lerp(a.y, b.y, u) + (dist > 1 ? (dx / dist) * arc : 0)
  }
  // The cursor rests and then, in the agentic act, steps back and lets the system work
  const opacity = seg(t, 0.9, 1.5) * (1 - seg(t, 29.7, 30.4)) + seg(t, 34.8, 35.4) * (1 - seg(t, 37.2, 37.8)) * (t > 30.4 ? 1 : 0)
  const press = CLICKS.reduce((p, c) => Math.min(p, 1 - 0.16 * Math.max(0, 1 - Math.abs(t - c.t) / 0.14)), 1)
  return { x, y, opacity: clamp01(opacity), press }
}

/* ───────── Camera ───────── */

/**
 * Landscape: the whole world, with a slow push-in across each act.
 * Portrait: a window that follows the action. Each key is [time, centre x, centre y, visible width in world pixels].
 */
const PORTRAIT_KEYS: readonly [number, number, number, number][] = [
  [0, 800, 420, 1250],
  [3.4, 800, 380, 1250],
  [4.8, 800, 300, 1050],
  [6.6, 800, 300, 1050],
  [7.4, 650, 330, 1000],
  [8.4, 420, 380, 900],
  [9.6, 560, 420, 1000],
  [10.3, 1060, 440, 780],
  [11.8, 1060, 440, 780],
  [12.8, 700, 300, 1150],
  [15.4, 800, 300, 950],
  [16.6, 800, 620, 1100],
  [17.8, 800, 620, 1100],
  [18.8, 330, 420, 780],
  [21.0, 330, 420, 780],
  [22.0, 1010, 420, 950],
  [23.6, 1010, 420, 950],
  [24.4, 330, 300, 780],
  [25.8, 330, 300, 780],
  [26.5, 330, 380, 780],
  [27.2, 330, 380, 780],
  [27.9, 1010, 430, 950],
  [29.0, 1010, 430, 950],
  [29.6, 400, 470, 900],
  [33.0, 1200, 470, 900],
  [34.2, 800, 430, 720],
  [37.0, 800, 430, 720],
  [38.0, 460, 360, 950],
  [40.0, 1000, 420, 1000],
  [41.8, 800, 450, 1150],
  [48, 800, 450, 1150],
]

export const cameraAt = (t: number, portrait: boolean): { cx: number; cy: number; z: number; w: number } => {
  if (portrait) {
    let k = 0
    while (k < PORTRAIT_KEYS.length - 2 && t >= PORTRAIT_KEYS[k + 1][0]) k++
    const a = PORTRAIT_KEYS[k]
    const b = PORTRAIT_KEYS[k + 1]
    const u = smooth(clamp01((t - a[0]) / (b[0] - a[0])))
    return { cx: lerp(a[1], b[1], u), cy: lerp(a[2], b[2], u), z: 1, w: lerp(a[3], b[3], u) }
  }
  let k = 0
  while (k < ACTS.length - 1 && t >= ACTS[k + 1].start) k++
  const start = ACTS[k].start
  const end = k < ACTS.length - 1 ? ACTS[k + 1].start : STORY
  const u = clamp01((t - start) / (end - start))
  // Alternate the drift direction act by act so the camera never feels like it is stuck on one rail
  const dir = k % 2 === 0 ? 1 : -1
  return { cx: WORLD_W / 2 + dir * (u - 0.5) * 26, cy: WORLD_H / 2 + (0.5 - u) * 12, z: 1.0 + 0.035 * u, w: WORLD_W }

}
