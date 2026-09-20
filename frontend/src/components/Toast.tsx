import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"

interface ToastState {
  message: string
  action?: { label: string; onClick: () => void }
}

interface ToastApi {
  showToast: (message: string, action?: ToastState["action"]) => void
}

const ToastContext = createContext<ToastApi | null>(null)

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error("useToast must be used within ToastProvider")
  return ctx
}

const DISMISS_MS = 6000

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastState | null>(null)
  const timer = useRef<number | null>(null)

  const clearTimer = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current)
      timer.current = null
    }
  }, [])

  const showToast = useCallback(
    (message: string, action?: ToastState["action"]) => {
      clearTimer()
      setToast({ message, action })
      timer.current = window.setTimeout(() => setToast(null), DISMISS_MS)
    },
    [clearTimer],
  )

  useEffect(() => clearTimer, [clearTimer])

  const api = useMemo(() => ({ showToast }), [showToast])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex justify-center px-4">
        {toast && (
          <div
            role="status"
            className="pointer-events-auto flex items-center gap-4 rounded-xl bg-slate-900 px-4 py-3 text-sm text-white shadow-lg"
          >
            <span>{toast.message}</span>
            {toast.action && (
              <button
                type="button"
                onClick={() => {
                  clearTimer()
                  setToast(null)
                  toast.action?.onClick()
                }}
                className="rounded-lg bg-white/10 px-2.5 py-1 text-xs font-semibold text-brand hover:bg-white/20"
              >
                {toast.action.label}
              </button>
            )}
          </div>
        )}
      </div>
    </ToastContext.Provider>
  )
}
