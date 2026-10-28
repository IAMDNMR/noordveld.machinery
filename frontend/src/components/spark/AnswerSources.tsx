import { Check, ChevronDown, CircleAlert, LockKeyhole } from 'lucide-react'
import type { SparkResponse } from '../../api/spark'
import { ProvenanceBadge } from '../intelligence/provenance'

const STEP_STATUS = {
  completed: 'Done',
  failed: 'Unavailable',
  access_denied: 'Access needed',
  sign_in_required: 'Sign in needed',
} as const

const DEMO_CLASSES = ['SYNTHETIC_DEMO', 'TEST_DATA']

/** What Spark did, which data classes the answer rests on and when it was answered. Only facts the API returned. */
export function AnswerSources({ response, at }: { response: SparkResponse; at?: number }) {
  const provenance = response.intelligence?.provenance ?? []
  const shoppingSteps = response.shopping?.steps.filter((step) => step.status !== 'skipped') ?? []
  const demo = provenance.some((item) => DEMO_CLASSES.includes(item.data_class))
  if (!response.steps.length && !shoppingSteps.length && !provenance.length) return null
  return (
    <details className="spark-sources">
      <summary>
        Sources and steps
        <ChevronDown size={14} aria-hidden="true" />
      </summary>
      <div className="spark-sources__body">
        {response.steps.length || shoppingSteps.length ? (
          <section aria-label="Steps">
            <h3>Steps</h3>
            <ol>
              {response.steps.map((step, i) => (
                <li key={i}>
                  {step.status === 'completed' ? (
                    <Check size={13} aria-hidden="true" />
                  ) : step.status === 'sign_in_required' || step.status === 'access_denied' ? (
                    <LockKeyhole size={13} aria-hidden="true" />
                  ) : (
                    <CircleAlert size={13} aria-hidden="true" />
                  )}
                  <span>
                    {step.label} · {STEP_STATUS[step.status]}
                  </span>
                </li>
              ))}
              {shoppingSteps.map((step) => (
                <li key={step.key}>
                  <span>
                    {step.label}: {step.message}
                  </span>
                </li>
              ))}
            </ol>
          </section>
        ) : null}
        {provenance.length ? (
          <section aria-label="Data sources">
            <h3>Data sources</h3>
            <p className="spark-sources__meta">
              {provenance.map((item) => (
                <span key={item.data_class}>
                  <ProvenanceBadge value={item.data_class} /> {item.count}{' '}
                </span>
              ))}
            </p>
            {demo ? (
              <p className="spark-sources__meta">
                Some records are synthetic demonstration data, not live enterprise information.
              </p>
            ) : null}
          </section>
        ) : null}
        {at ? (
          <p className="spark-sources__meta">
            Answered{' '}
            <time dateTime={new Date(at).toISOString()}>
              {new Date(at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
            </time>
            . Stock and prices can change; confirm before ordering.
          </p>
        ) : null}
      </div>
    </details>
  )
}
