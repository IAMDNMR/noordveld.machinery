import type { StageId } from '../data/stages'

export type FilmFormat = 'landscape' | 'square' | 'vertical'

export const FILM_FPS = 30
export const FILM_SECONDS = 30
export const FILM_FRAMES = FILM_FPS * FILM_SECONDS

export const FORMATS: Record<FilmFormat, { width: number; height: number }> = {
  landscape: { width: 1920, height: 1080 },
  square: { width: 1080, height: 1080 },
  vertical: { width: 1080, height: 1920 },
}

export interface Act {
  id: StageId
  kicker: string
  lines: readonly string[]
  start: number
  end: number
  /** Window (seconds) during which the scene animates from 0 → 1. */
  scene: readonly [number, number]
}

/** Storyboard: 0–5 commerce, 5–10 e-commerce, 10–15 quick commerce, 15–25 agentic, 25–30 outcome. */
export const acts: readonly Act[] = [
  { id: 'commerce', kicker: 'COMMERCE', lines: ['I need something.'], start: 0, end: 5, scene: [0.6, 4.4] },
  { id: 'e-commerce', kicker: 'E-COMMERCE', lines: ['I know what', 'I want.'], start: 5, end: 10, scene: [5.5, 9.4] },
  { id: 'quick-commerce', kicker: 'QUICK COMMERCE', lines: ['Get it to me', 'quickly.'], start: 10, end: 15, scene: [10.5, 14.4] },
  { id: 'agentic-e-commerce', kicker: 'AGENTIC E-COMMERCE', lines: ['I have a need.', 'Understand it and', 'help me solve it.'], start: 15, end: 25, scene: [15.8, 24.2] },
]

export const OUTCOME_START = 25
export const CROSSFADE = 0.6

export interface Layout {
  width: number
  height: number
  scene: { x: number; y: number; w: number; h: number }
  text: { x: number; y: number; kicker: number; line: number; leading: number }
  outcome: { x: number; y: number; line: number; leading: number }
  rail: { y: number; x: number; w: number; font: number }
}

export function layoutFor(format: FilmFormat): Layout {
  const { width, height } = FORMATS[format]
  if (format === 'landscape') {
    return {
      width, height,
      scene: { x: 940, y: 230, w: 880, h: 550 },
      text: { x: 130, y: 420, kicker: 30, line: 80, leading: 96 },
      outcome: { x: width / 2, y: 520, line: 96, leading: 112 },
      rail: { y: 990, x: 130, w: width - 260, font: 24 },
    }
  }
  if (format === 'square') {
    return {
      width, height,
      scene: { x: 90, y: 440, w: 900, h: 562 },
      text: { x: 90, y: 190, kicker: 28, line: 64, leading: 76 },
      outcome: { x: width / 2, y: 520, line: 68, leading: 84 },
      rail: { y: 1040, x: 90, w: width - 180, font: 22 },
    }
  }
  return {
    width, height,
    scene: { x: 90, y: 900, w: 900, h: 562 },
    text: { x: 90, y: 380, kicker: 32, line: 86, leading: 102 },
    outcome: { x: width / 2, y: 860, line: 66, leading: 84 },
    rail: { y: 1790, x: 90, w: width - 180, font: 24 },
  }
}
