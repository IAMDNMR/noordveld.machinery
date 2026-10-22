import { Users } from 'lucide-react'
import { Empty } from '../bits'
import type { ViewProps } from './types'

/** Who may do what. The matrices are derived from the process steps, so they cannot disagree with the process. */
export function RolesView({ studio, recent, ask }: ViewProps) {
  const { definition } = studio
  const business = definition.business
  const steps = definition.workflow_definitions.flatMap((workflow) =>
    workflow.states.map((state) => ({ workflow, state })),
  )
  const owned = (roleId: string) => steps.filter(({ state }) => state.role_id === roleId)
  const access = (roleId: string, entityId: string) => {
    const role = business.roles.find((item) => item.id === roleId)
    if (business.entities.find((item) => item.id === entityId)?.owner_role_id === roleId) return 'W'
    const mine = owned(roleId).filter(
      ({ state }) => state.permission && role?.permissions.includes(state.permission),
    )
    const writes = mine.some(({ state }) => (state.writes_entity_ids ?? []).includes(entityId))
    const reads = mine.some(({ state }) => (state.reads_entity_ids ?? []).includes(entityId))
    return writes ? 'W' : reads ? 'R' : ''
  }
  const entities = business.entities.filter((entity) =>
    business.roles.some((role) => access(role.id, entity.id)),
  )

  if (!business.roles.length)
    return (
      <Empty icon={<Users size={28} />} title="No roles yet">
        Say who uses the application and what each person does — for example “planners create
        requests and dispatchers assign carriers” — and the roles and their access boundaries appear
        here.
      </Empty>
    )
  return (
    <div className="sw-view">
      <section className="sw-card" aria-label="Roles">
        <div className="sw-card__head">
          <h3>
            Roles <span className="sw-count">{business.roles.length}</span>
          </h3>
          <button type="button" className="sw-button" onClick={() => ask('Add a role: ')}>
            Add a role
          </button>
        </div>
        <ul className="sw-roles">
          {business.roles.map((role) => {
            const mine = owned(role.id)
            return (
              <li key={role.id} data-changed={recent.has(role.id) || undefined}>
                <div>
                  <strong>{role.name}</strong>
                  {role.responsibilities.length ? (
                    <p className="sw-muted">{role.responsibilities.join(' · ')}</p>
                  ) : null}
                  <p className="sw-muted">
                    {mine.length
                      ? `Performs ${mine.length} step${mine.length === 1 ? '' : 's'}: ${mine
                          .map(({ state }) => state.label)
                          .slice(0, 4)
                          .join(', ')}${mine.length > 4 ? '…' : ''}`
                      : 'Performs no step yet.'}
                  </p>
                  {role.approval_authority?.length ? (
                    <p className="sw-muted">May approve: {role.approval_authority.join(', ')}</p>
                  ) : null}
                </div>
                <details>
                  <summary>Technical permissions · {role.permissions.length}</summary>
                  <ul className="sw-tags sw-tags--code" aria-label={`${role.name} permissions`}>
                    {role.permissions.length ? (
                      role.permissions.map((permission) => (
                        <li key={permission}>
                          <code>{permission}</code>
                        </li>
                      ))
                    ) : (
                      <li>no permissions</li>
                    )}
                  </ul>
                </details>
              </li>
            )
          })}
        </ul>
      </section>
      <section className="sw-card" aria-label="Data access">
        <h3>Access boundaries</h3>
        <p className="sw-muted">
          Read (R) and update (W) access includes entity ownership and permitted process steps. Only
          the owner role can create an owned record. Fields maintained by another role remain
          read-only. The generated application checks access on its server.
        </p>
        {entities.length === 0 ? (
          <p className="sw-muted">No role touches any data yet.</p>
        ) : (
          <div className="sw-scroll">
            <table className="sw-table sw-matrix">
              <thead>
                <tr>
                  <th>Data</th>
                  {business.roles.map((role) => (
                    <th key={role.id}>{role.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {entities.map((entity) => (
                  <tr key={entity.id}>
                    <th scope="row">{entity.name}</th>
                    {business.roles.map((role) => {
                      const value = access(role.id, entity.id)
                      return (
                        <td key={role.id} data-access={value || undefined}>
                          {value || '·'}
                          <span className="sw-sr">
                            {value === 'W'
                              ? 'can change'
                              : value === 'R'
                                ? 'can read'
                                : 'no access'}
                          </span>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <p className="sw-muted sw-aside">
        Want to change who may do something? Ask in plain words — for example “only the warehouse
        manager may approve a dispatch”.
      </p>
    </div>
  )
}
