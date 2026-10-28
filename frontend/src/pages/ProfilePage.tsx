import { useState, type CSSProperties, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import {
  eraseProfile,
  getProfile,
  saveProfile,
  type Profile,
  type ProfileState,
} from '../api/profile'
import { getCountries, getDealers, getDestinations } from '../api/orders'
import { useApi } from '../hooks/useApi'
import { CineHero } from '../components/cine/Cine'
import { usePageMeta } from '../hooks/usePageMeta'
import { useSession } from '../store/session'
import './profile.css'

const EMPTY: Profile = {
  machines: [],
  preferred_machine: null,
  country: null,
  ship_to_id: null,
  dealer_id: null,
  name: null,
  company: null,
  email: null,
  phone: null,
  receiver_name: null,
  receiver_phone: null,
  delivery_preference: null,
  delivery_notes: null,
}

export default function ProfilePage() {
  usePageMeta({
    title: 'My profile',
    description:
      'Saved machine, delivery and contact details that Spark uses so you do not repeat yourself.',
    path: '/profile',
  })
  const { user, ready } = useSession()
  const state = useApi((signal) => getProfile(signal), `profile:${user?.id ?? ''}`)
  if (!ready) return null
  if (!user)
    return (
      <div className="pf-page">
        <CineHero
          id="profile-title"
          tone="light"
          eyebrow="Your profile"
          lines={['Tell Spark once.', 'Never repeat yourself.']}
          lead={
            <p>
              <Link to="/sign-in?next=/profile">Sign in</Link> to manage the details Spark can
              remember for you.
            </p>
          }
        />
      </div>
    )
  return (
    <div className="pf-page">
      <CineHero
        id="profile-title"
        tone="light"
        eyebrow="Your profile"
        lines={['Tell Spark once.', 'Never repeat yourself.']}
        lead={
          <p>
            Save your machine, delivery site and contact details so Spark and checkout can fill them
            in. Nothing is stored unless you agree, you can erase it at any time, and every order
            still shows each detail for your confirmation.
          </p>
        }
      />
      <div className="wf-container pf">
        {state.error ? (
          <p role="alert">Your profile could not be loaded. Try again later.</p>
        ) : null}
        {state.data ? <ProfileForm initial={state.data} /> : state.loading ? <p>Loading…</p> : null}
      </div>
    </div>
  )
}

function ProfileForm({ initial }: { initial: ProfileState }) {
  const [saved, setSaved] = useState(initial)
  const [value, setValue] = useState<Profile>({
    ...EMPTY,
    ...(initial.profile ?? {
      name: initial.account.name.replace(/ \(demo\)$/, ''),
      email: initial.account.email,
      company: initial.account.company,
    }),
  })
  const [consent, setConsent] = useState(initial.stored)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const countries = useApi((signal) => getCountries(signal), 'profile-countries')
  const country = value.country ?? ''
  const sites = useApi(
    (signal) => (country ? getDestinations(country, signal) : Promise.resolve([])),
    `profile-sites:${country}`,
  )
  const dealers = useApi(
    (signal) => getDealers(country || null, signal),
    `profile-dealers:${country}`,
  )
  const set = (patch: Partial<Profile>) => setValue((current) => ({ ...current, ...patch }))
  const text = (key: keyof Profile) => (value[key] as string | null) ?? ''
  const run = async (action: () => Promise<ProfileState>, done: string) => {
    setBusy(true)
    setMessage('')
    try {
      const next = await action()
      setSaved(next)
      setConsent(next.stored)
      setMessage(done)
    } catch {
      setMessage('That did not work. Nothing was changed.')
    } finally {
      setBusy(false)
    }
  }
  const submit = (event: FormEvent) => {
    event.preventDefault()
    const clean = Object.fromEntries(
      Object.entries(value).map(([key, entry]) => [key, entry === '' ? null : entry]),
    ) as Partial<Profile>
    void run(
      () => saveProfile(clean, consent),
      consent ? 'Profile saved.' : 'Consent withdrawn. Your stored profile was erased.',
    )
  }
  const field = (key: keyof Profile, label: string, type = 'text') => (
    <label>
      {label}
      <input
        type={type}
        maxLength={200}
        value={text(key)}
        onChange={(event) => set({ [key]: event.target.value } as Partial<Profile>)}
      />
    </label>
  )
  const known = KNOWN.map((item) => ({ ...item, set: item.has(value) }))
  const share = known.filter((item) => item.set).length / known.length
  return (
    <div className="pf-layout">
      <aside className="pf-side" aria-label="What Spark can use">
        <div className="pf-ring" style={{ '--share': share } as CSSProperties}>
          <svg viewBox="0 0 120 120" aria-hidden="true">
            <circle cx="60" cy="60" r="50" pathLength={1} />
            <circle className="pf-ring__fill" cx="60" cy="60" r="50" pathLength={1} />
          </svg>
          <div>
            <strong>{Math.round(share * 100)}%</strong>
            <span>{consent ? 'ready to use' : 'not stored'}</span>
          </div>
        </div>
        <p className="pf-side__lead">
          {saved.stored
            ? 'Spark uses these saved details instead of asking you again.'
            : 'Nothing is stored yet. Spark asks for these details on every order.'}
        </p>
        <ul className="pf-known">
          {known.map((item) => (
            <li key={item.label} data-set={item.set}>
              <i aria-hidden="true" />
              {item.label}
              <span>{item.set ? 'Saved' : 'Spark will ask'}</span>
            </li>
          ))}
        </ul>
      </aside>
      <form className="pf-form" onSubmit={submit}>
        <fieldset>
          <legend>Machine</legend>
          {field('preferred_machine', 'Preferred machine model')}
          <label>
            Other machine models (comma separated)
            <input
              value={value.machines.join(', ')}
              onChange={(event) =>
                set({
                  machines: event.target.value
                    .split(',')
                    .map((item) => item.trim())
                    .filter(Boolean)
                    .slice(0, 5),
                })
              }
            />
          </label>
          <small>Spark only uses a model when the catalogue records that the part fits it.</small>
        </fieldset>
        <fieldset>
          <legend>Delivery</legend>
          <label>
            Country
            <select
              value={country}
              onChange={(event) =>
                set({ country: event.target.value || null, ship_to_id: null, dealer_id: null })
              }
            >
              <option value="">Not set</option>
              {(countries.data ?? []).map((item) => (
                <option key={item.country_code} value={item.country_code}>
                  {item.country_code}
                </option>
              ))}
            </select>
          </label>
          <label>
            Default delivery site
            <select
              value={value.ship_to_id ?? ''}
              onChange={(event) => set({ ship_to_id: event.target.value || null })}
            >
              <option value="">Not set</option>
              {(sites.data ?? []).map((site) => (
                <option key={site.ship_to_id} value={site.ship_to_id}>
                  {site.city} — {site.street}
                </option>
              ))}
            </select>
          </label>
          <label>
            Preferred dealer
            <select
              value={value.dealer_id ?? ''}
              onChange={(event) => set({ dealer_id: event.target.value || null })}
            >
              <option value="">Not set</option>
              {(dealers.data ?? []).map((dealer) => (
                <option key={dealer.dealer_id} value={dealer.dealer_id}>
                  {dealer.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            When several options exist, prefer
            <select
              value={value.delivery_preference ?? ''}
              onChange={(event) =>
                set({
                  delivery_preference: (event.target.value ||
                    null) as Profile['delivery_preference'],
                })
              }
            >
              <option value="">Ask me each time</option>
              <option value="fastest">Fastest delivery</option>
              <option value="cheapest">Lowest total cost</option>
            </select>
          </label>
          {field('receiver_name', 'Person receiving deliveries')}
          {field('receiver_phone', 'Receiver’s phone', 'tel')}
        </fieldset>
        <fieldset>
          <legend>Contact</legend>
          {field('name', 'Name')}
          {field('company', 'Company')}
          {field('email', 'Email', 'email')}
          {field('phone', 'Phone', 'tel')}
        </fieldset>
        <label className="pf-consent">
          <input
            type="checkbox"
            checked={consent}
            onChange={(event) => setConsent(event.target.checked)}
          />
          <span>
            I agree that Noordveld stores these details to pre-fill my orders and Spark answers. I
            can withdraw this at any time; unticking and saving erases them.
          </span>
        </label>
        <div className="pf-actions">
          <button type="submit" disabled={busy} className="btn btn-primary">
            {consent ? 'Save profile' : 'Save (nothing is stored without consent)'}
          </button>
          {saved.stored ? (
            <button
              type="button"
              disabled={busy}
              className="btn btn-secondary"
              onClick={() => void run(eraseProfile, 'Your profile was erased.')}
            >
              Erase my profile
            </button>
          ) : null}
        </div>
        <p role="status">
          {message ||
            (saved.stored
              ? `Stored with your consent on ${saved.consent_at?.slice(0, 10)}.`
              : 'No profile is stored.')}
        </p>
      </form>
    </div>
  )
}

const KNOWN: { label: string; has: (p: Profile) => boolean }[] = [
  { label: 'Machine', has: (p) => Boolean(p.preferred_machine || p.machines.length) },
  { label: 'Delivery site', has: (p) => Boolean(p.ship_to_id) },
  { label: 'Dealer', has: (p) => Boolean(p.dealer_id) },
  { label: 'Delivery preference', has: (p) => Boolean(p.delivery_preference) },
  { label: 'Receiver', has: (p) => Boolean(p.receiver_name && p.receiver_phone) },
  { label: 'Your contact details', has: (p) => Boolean(p.name && p.email && p.phone) },
]
