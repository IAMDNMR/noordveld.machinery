import type { CSSProperties } from 'react'
import type { ThemePreset } from '../api/appTemplates'

/** System font stacks only: a generated application loads nothing from the network. */
const FONTS: Record<ThemePreset['font_heading'], string> = {
  grotesk: "'Segoe UI Variable Display', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
  humanist: "'Segoe UI', Candara, 'Gill Sans', 'Trebuchet MS', sans-serif",
  serif: "Georgia, 'Iowan Old Style', 'Palatino Linotype', 'Times New Roman', serif",
  mono: "'Cascadia Mono', Consolas, 'SF Mono', monospace",
  system: "system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif",
}

const GAP = { compact: 12, comfortable: 18, spacious: 26 }
const SHADOW = {
  none: 'none',
  soft: '0 1px 2px rgba(15, 23, 42, 0.06), 0 8px 24px rgba(15, 23, 42, 0.06)',
  crisp: '0 1px 0 rgba(15, 23, 42, 0.08), 0 2px 6px rgba(15, 23, 42, 0.08)',
}

/** The theme's design tokens as CSS custom properties; every engine style reads only these. */
export function themeStyle(theme: ThemePreset): CSSProperties {
  const c = theme.colors
  return {
    '--ta-primary': c.primary,
    '--ta-primary-text': c.primary_text,
    '--ta-accent': c.accent,
    '--ta-bg': c.background,
    '--ta-surface': c.surface,
    '--ta-surface-alt': c.surface_alt,
    '--ta-text': c.text,
    '--ta-muted': c.muted,
    '--ta-border': c.border,
    '--ta-nav-bg': c.nav_background,
    '--ta-nav-text': c.nav_text,
    '--ta-success': c.success,
    '--ta-warning': c.warning,
    '--ta-danger': c.danger,
    '--ta-font-heading': FONTS[theme.font_heading],
    '--ta-font-body': FONTS[theme.font_body],
    '--ta-gap': `${GAP[theme.density]}px`,
    '--ta-radius': `${theme.radius}px`,
    '--ta-shadow': SHADOW[theme.shadow],
    '--ta-control': theme.touch ? '48px' : theme.density === 'compact' ? '34px' : '40px',
  } as CSSProperties
}
