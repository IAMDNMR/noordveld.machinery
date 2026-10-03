/* Optional sound: a soft tick on every click and a quiet two-note chime when the order is confirmed. Off by default. */

let ctx: AudioContext | null = null

export const enableSound = (): void => {
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!Ctor) return
  ctx ??= new Ctor()
  void ctx.resume()
}

const tone = (freq: number, start: number, length: number, peak: number, type: OscillatorType = 'sine'): void => {
  if (!ctx) return
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.type = type
  osc.frequency.setValueAtTime(freq, ctx.currentTime + start)
  gain.gain.setValueAtTime(0.0001, ctx.currentTime + start)
  gain.gain.exponentialRampToValueAtTime(peak, ctx.currentTime + start + 0.008)
  gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + start + length)
  osc.connect(gain).connect(ctx.destination)
  osc.start(ctx.currentTime + start)
  osc.stop(ctx.currentTime + start + length + 0.02)
}

export const playClick = (): void => {
  tone(1900, 0, 0.05, 0.05, 'triangle')
  tone(520, 0, 0.09, 0.03)
}

export const playConfirm = (): void => {
  tone(659.25, 0, 0.5, 0.035)
  tone(987.77, 0.12, 0.7, 0.03)
}
