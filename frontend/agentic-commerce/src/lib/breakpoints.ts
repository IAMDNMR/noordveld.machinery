/** Keep in sync with the breakpoint note in styles/tokens.css. */
export const breakpoints = { tablet: 720, laptop: 1024, desktop: 1360 } as const

export const queries = {
  belowTablet: `(max-width: ${breakpoints.tablet - 1}px)`,
  belowLaptop: `(max-width: ${breakpoints.laptop - 1}px)`,
  reducedMotion: '(prefers-reduced-motion: reduce)',
} as const
