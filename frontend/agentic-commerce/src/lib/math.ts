export const clamp01 = (x: number): number => Math.min(1, Math.max(0, x))
export const lerp = (a: number, b: number, t: number): number => a + (b - a) * t
export const easeInOut = (t: number): number => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
export const easeOut = (t: number): number => 1 - Math.pow(1 - t, 3)
export const linear = (t: number): number => t

/** Eased progress of `p` through the window [a, b]. Pure, so scenes are deterministic for any frame. */
export const seg = (p: number, a: number, b: number, ease: (t: number) => number = easeInOut): number =>
  ease(clamp01((p - a) / (b - a)))
