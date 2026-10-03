import logoDark from '../assets/brand/logo.png'
import logoLight from '../assets/brand/logo-reversed.png'

interface LogoProps {
  /** 'light' is the reversed logo for dark backgrounds */
  tone: 'dark' | 'light'
  height?: number
}

export function Logo({ tone, height = 34 }: LogoProps) {
  return <img src={tone === 'light' ? logoLight : logoDark} alt="Noordveld Machinery B.V." height={height} width={Math.round(height * 4.46)} style={{ height, width: 'auto' }} decoding="async" />
}
