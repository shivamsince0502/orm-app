import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom"
import { getMe, logout } from "../api/client"

interface AuthApi {
  email: string | null
  setEmail: (email: string) => void
}

const AuthContext = createContext<AuthApi | null>(null)

export function useAuth(): AuthApi {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [email, setEmail] = useState<string | null>(null)
  const setEmailSafe = useCallback(
    (value: string) => setEmail(value.trim() ? value : null),
    [],
  )
  const api = useMemo(() => ({ email, setEmail: setEmailSafe }), [email, setEmailSafe])
  return <AuthContext.Provider value={api}>{children}</AuthContext.Provider>
}

function Header() {
  const navigate = useNavigate()
  const { email, setEmail } = useAuth()

  const signOut = () => {
    void logout().finally(() => {
      setEmail("")
      navigate("/login", { replace: true })
    })
  }

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-5xl items-center gap-3 px-4">
        <img
          src="/assets/brand/practice-by-numbers-logo.svg"
          alt="Practice by Numbers"
          className="h-8 w-8"
        />
        <span className="text-sm font-semibold tracking-tight text-slate-900">
          Practice by Numbers
        </span>
        <span className="text-sm text-slate-300">/</span>
        <span className="text-sm font-medium text-slate-600">Follow-Up Queue</span>
        <span className="ml-auto hidden text-xs font-medium text-slate-500 sm:block">
          {email}
        </span>
        <img
          src="/assets/avatars/sarah-jenkins.jpg"
          alt="Sarah Jenkins"
          title="Sarah Jenkins"
          className="h-9 w-9 rounded-full object-cover ring-2 ring-white"
        />
        <button
          type="button"
          onClick={signOut}
          className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs font-semibold text-slate-600 transition hover:border-red-300 hover:text-red-600"
        >
          Log out
        </button>
      </div>
    </header>
  )
}

type GateState = "loading" | "authed" | "anon"

/** Guards protected routes: checks the session cookie via /api/auth/me/. */
export function RequireAuth() {
  const { setEmail } = useAuth()
  const location = useLocation()
  const [state, setState] = useState<GateState>("loading")

  useEffect(() => {
    let cancelled = false
    getMe()
      .then((me) => {
        if (!cancelled) {
          setEmail(me.email)
          setState("authed")
        }
      })
      .catch(() => {
        if (!cancelled) setState("anon")
      })
    return () => {
      cancelled = true
    }
  }, [setEmail])

  if (state === "loading") {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-brand/30 border-t-brand" />
      </div>
    )
  }
  if (state === "anon") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return (
    <div className="min-h-screen bg-slate-50">
      <Header />
      <main>
        <Outlet />
      </main>
    </div>
  )
}
