import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { errorMessage, requestOtp, verifyOtp } from "../api/client"
import { useAuth } from "../components/Auth"
import { useToast } from "../components/Toast"

export default function LoginPage() {
  const navigate = useNavigate()
  const { setEmail } = useAuth()
  const { showToast } = useToast()

  const [step, setStep] = useState<"email" | "code">("email")
  const [email, setEmailField] = useState("")
  const [code, setCode] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [cooldown, setCooldown] = useState(0)

  useEffect(() => {
    if (cooldown <= 0) return
    const timer = window.setTimeout(() => setCooldown((c) => c - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [cooldown])

  const request = async () => {
    if (!email.trim()) {
      setError("Enter your email.")
      return
    }
    setBusy(true)
    setError(null)
    try {
      const result = await requestOtp(email.trim().toLowerCase())
      setCooldown(result.cooldown_seconds)
      setStep("code")
    } catch (err) {
      setError(errorMessage(err, "Could not send the code."))
    } finally {
      setBusy(false)
    }
  }

  const resend = async () => {
    if (cooldown > 0) return
    setError(null)
    try {
      const result = await requestOtp(email.trim().toLowerCase())
      setCooldown(result.cooldown_seconds)
      showToast("New code sent")
    } catch (err) {
      setError(errorMessage(err, "Could not resend the code."))
    }
  }

  const verify = async () => {
    if (!/^\d{6}$/.test(code)) {
      setError("Enter the 6-digit code.")
      return
    }
    setBusy(true)
    setError(null)
    try {
      const me = await verifyOtp(email.trim().toLowerCase(), code)
      setEmail(me.email)
      navigate("/", { replace: true })
    } catch (err) {
      setError(errorMessage(err, "Verification failed."))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-4">
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-7 shadow-sm">
        <div className="mb-6 text-center">
          <img
            src="/assets/brand/practice-by-numbers-logo.svg"
            alt=""
            className="mx-auto h-10 w-10"
          />
          <h1 className="mt-3 text-lg font-bold text-slate-900">Sign in to Follow-Up Queue</h1>
          <p className="mt-1 text-sm text-slate-500">
            {step === "email"
              ? "We'll email you a one-time login code."
              : `Enter the 6-digit code sent to ${email}.`}
          </p>
        </div>

        {step === "email" ? (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              void request()
            }}
          >
            <input
              type="email"
              required
              autoFocus
              value={email}
              onChange={(e) => setEmailField(e.target.value)}
              placeholder="you@company.com"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
            />
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-dark disabled:opacity-60"
            >
              {busy ? "Sending…" : "Send login code"}
            </button>
          </form>
        ) : (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              void verify()
            }}
          >
            <input
              inputMode="numeric"
              pattern="\d{6}"
              maxLength={6}
              required
              autoFocus
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              placeholder="000000"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-center text-xl font-semibold tracking-[0.5em] focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
            />
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-dark disabled:opacity-60"
            >
              {busy ? "Verifying…" : "Verify & sign in"}
            </button>
            <div className="flex items-center justify-between text-xs">
              <button
                type="button"
                onClick={() => {
                  setStep("email")
                  setCode("")
                }}
                className="font-medium text-slate-500 hover:text-slate-700"
              >
                ← Use another email
              </button>
              <button
                type="button"
                disabled={cooldown > 0 || busy}
                onClick={() => void resend()}
                className="font-medium text-brand-dark hover:underline disabled:text-slate-300 disabled:no-underline"
              >
                {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend code"}
              </button>
            </div>
          </form>
        )}

        {error && <p className="mt-4 text-center text-sm font-medium text-red-600">{error}</p>}
      </div>
    </div>
  )
}
