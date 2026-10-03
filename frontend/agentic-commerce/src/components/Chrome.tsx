import { PlainLink } from '../../../src/components/chrome/PlainLink'
import { SiteFooter } from '../../../src/components/chrome/SiteFooter'
import { SiteNav } from '../../../src/components/chrome/SiteNav'

/** The same navigation bar and footer as the rest of the Noordveld site. This page is a separate document, so links are plain anchors. */
export const Nav = () => <SiteNav pathname="/agentic-commerce/" heroTone={false} Link={PlainLink} />
export const Footer = () => <SiteFooter Link={PlainLink} />
