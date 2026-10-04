import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { getMe, signIn as apiSignIn, signOut as apiSignOut, type Me } from '../api/orders'

interface SessionValue {
  /** The signed-in user as the backend resolves it; null when signed out. The role here only shapes the interface. */
  user: Me | null
  ready: boolean
  signIn: (userId: string) => Promise<Me>
  signOut: () => Promise<void>
}

const Session = createContext<SessionValue | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const ctrl = new AbortController()
    getMe(ctrl.signal).then(
      (me) => {
        setUser(me)
        setReady(true)
      },
      () => {
        if (!ctrl.signal.aborted) setReady(true) // 401: signed out
      },
    )
    return () => ctrl.abort()
  }, [])

  const signIn = useCallback(async (userId: string) => {
    const me = await apiSignIn(userId)
    setUser(me)
    return me
  }, [])
  const signOut = useCallback(async () => {
    await apiSignOut().catch(() => undefined)
    try {
      localStorage.removeItem('noordveld-parts-cart-v2') // the user's cart stays on the server; this browser keeps no copy
    } catch {
      /* storage unavailable */
    }
    setUser(null)
  }, [])

  const value = useMemo(() => ({ user, ready, signIn, signOut }), [user, ready, signIn, signOut])
  return <Session.Provider value={value}>{children}</Session.Provider>
}

/** The session, or a signed-out stand-in where no provider is mounted (the separate explainer page, tests). */
export function useSession(): SessionValue {
  return useContext(Session) ?? { user: null, ready: true, signIn: () => Promise.reject(new Error('No session')), signOut: () => Promise.resolve() }
}

export const roleLabel = (role: Me['role']): string => (role === 'ORDER_PROCESSOR' ? 'Order Processor' : 'End User')
