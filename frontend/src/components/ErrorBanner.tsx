import { ApiError } from "../api/client"

function message(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 503) return "AI service unavailable — check the LLM endpoint/API key"
    if (error.status === 502) return "AI returned unparseable output"
    return error.detail ?? "Something went wrong"
  }
  return "Something went wrong"
}

export default function ErrorBanner({
  error,
  onRetry,
}: {
  error: unknown
  onRetry: () => void
}) {
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm font-medium text-red-700">{message(error)}</p>
        <button
          type="button"
          onClick={onRetry}
          className="rounded-lg bg-red-600 px-3 py-1.5 text-sm font-semibold text-white shadow-sm hover:bg-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
        >
          Retry
        </button>
      </div>
    </div>
  )
}
