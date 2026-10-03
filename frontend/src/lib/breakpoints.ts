/** Keep in sync with the breakpoint note in styles/tokens.css. */
export const breakpoints = { tablet: 760, laptop: 1100, desktop: 1440 } as const

export const queries = {
  belowTablet: `(max-width: ${breakpoints.tablet - 1}px)`,
  reducedMotion: '(prefers-reduced-motion: reduce)',
} as const
