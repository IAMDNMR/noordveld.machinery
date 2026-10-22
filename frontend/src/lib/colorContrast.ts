/** Choose the higher-contrast text color for an opaque hexadecimal surface. */
export function contrastInk(hex: string): '#000000' | '#ffffff' {
  if (!/^#[a-f0-9]{6}$/i.test(hex)) return '#ffffff'
  const channels = [1, 3, 5]
    .map((start) => parseInt(hex.slice(start, start + 2), 16) / 255)
    .map((value) => (value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4))
  const luminance = channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722
  return (luminance + 0.05) / 0.05 > 1.05 / (luminance + 0.05) ? '#000000' : '#ffffff'
}
