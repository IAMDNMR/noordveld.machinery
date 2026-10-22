import { Globe2, Sparkles } from 'lucide-react'
import type { IntakeState } from '../../api/studio'

export function OptionalSetup({
  intake,
  busy,
  act,
}: {
  intake: IntakeState
  busy: boolean
  act: (actions: Record<string, unknown>[]) => void
}) {
  if (!intake.questions.length)
    return (
      <p className="sw-muted sw-optional-done">
        <Sparkles size={15} /> Setup saved. The Studio will use your input and reusable process
        knowledge. You can request changes later.
      </p>
    )
  return (
    <section className="sw-card sw-optional-setup" aria-label="Optional setup">
      <div className="sw-optional-heading">
        <Globe2 size={20} />
        <div>
          <h3>A little context, a better starting point</h3>
          <p className="sw-muted">
            Two optional details. Skip them to keep building with the shared process draft.
          </p>
        </div>
      </div>
      <div className="sw-optional-grid">
        {intake.questions.slice(0, 2).map((question) => (
          <div key={question.id}>
            <label className="sw-field">
              <span>
                {question.text} <small>Optional</small>
              </span>
              <select
                disabled={busy}
                value=""
                onChange={(event) => {
                  if (event.target.value)
                    act([
                      {
                        type: 'set_intake_context',
                        [question.id === 'industry' ? 'industry_id' : 'region']: event.target.value,
                      },
                    ])
                }}
              >
                <option value="">Choose when you are ready</option>
                {question.options.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="sw-link-button"
              disabled={busy}
              onClick={() => act([{ type: 'set_intake_context', skip: [question.id] }])}
            >
              Skip this detail
            </button>
          </div>
        ))}
      </div>
      <footer>
        <span className="sw-muted">
          Skipped details remain unspecified. They never block Continue.
        </span>
        <button
          type="button"
          className="sw-button"
          disabled={busy}
          onClick={() =>
            act([{ type: 'set_intake_context', skip: intake.questions.map((q) => q.id) }])
          }
        >
          Skip setup
        </button>
      </footer>
    </section>
  )
}
