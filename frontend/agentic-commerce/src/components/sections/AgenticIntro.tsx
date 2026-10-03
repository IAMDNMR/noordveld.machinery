import { Reveal } from '../ui/Reveal'

export function AgenticIntro() {
  return (
    <section id="agentic" className="section on-night agentic-intro" aria-labelledby="agentic-title">
      <div className="container">
        <Reveal>
          <p className="eyebrow">What comes next</p>
        </Reveal>
        <Reveal delay={80}>
          <h2 id="agentic-title" className="display agentic-intro__title">
            Agentic E-Commerce
          </h2>
        </Reveal>
        <Reveal delay={160}>
          <p className="lead agentic-intro__lead">Every earlier chapter of commerce started with a product the customer already had in mind. This one starts with something harder, and more human: a requirement.</p>
        </Reveal>

        <figure className="requirement">
          <blockquote>
            <Reveal as="p" className="requirement__line requirement__line--lead" delay={0}>
              My machine is down.
            </Reveal>
            <Reveal as="p" className="requirement__line" delay={160}>
              I need it operational within two days.
            </Reveal>
            <Reveal as="p" className="requirement__line" delay={320}>
              My budget is <span className="accent-text">€80,000.</span>
            </Reveal>
          </blockquote>
          <Reveal as="figcaption" className="requirement__note" delay={480}>
            An example requirement, written for this demonstration. Not a live customer.
          </Reveal>
        </figure>
      </div>
    </section>
  )
}
