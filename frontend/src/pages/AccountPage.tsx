import { useCallback, useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import DraftModal from "../components/DraftModal"
import ErrorBanner from "../components/ErrorBanner"
import LogModal from "../components/LogModal"
import DetailSkeleton from "../components/Skeleton"
import TierPill from "../components/TierPill"
import TimelineItem from "../components/TimelineItem"
import { useToast } from "../components/Toast"
import { errorMessage, getAccount, postAction } from "../api/client"
import type { AccountDetail } from "../types"

function isoInDays(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

const SNOOZE_OPTIONS = [
  { label: "Tomorrow", days: 1 },
  { label: "3 days", days: 3 },
  { label: "1 week", days: 7 },
]

export default function AccountPage() {
  const { id } = useParams<{ id: string }>()
  const { showToast } = useToast()
  const [detail, setDetail] = useState<AccountDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)
  const [logOpen, setLogOpen] = useState(false)
  const [draftOpen, setDraftOpen] = useState(false)
  const [snoozeOpen, setSnoozeOpen] = useState(false)

  const fetchDetail = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      setDetail(await getAccount(id))
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    void fetchDetail()
  }, [fetchDetail])

  const runAction = async (
    action: Parameters<typeof postAction>[1],
    snoozeUntil?: string,
    toast?: string,
    undoable = false,
  ) => {
    if (!id) return
    try {
      await postAction(id, action, snoozeUntil)
      showToast(
        toast ?? "Done",
        undoable
          ? {
              label: "Undo",
              onClick: () => {
                void (async () => {
                  try {
                    await postAction(id, "undo")
                  } finally {
                    void fetchDetail()
                  }
                })()
              },
            }
          : undefined,
      )
      if (action === "pin" || action === "unpin" || action === "keep_open" || action === "release") {
        await fetchDetail() // re-rank with skeletons (D6)
        return
      }
      void fetchDetail()
    } catch (err) {
      showToast(errorMessage(err, "Action failed"))
    }
  }

  if (error) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-8">
        <Link to="/" className="mb-4 inline-block text-sm text-brand-dark hover:underline">
          ← Back to queue
        </Link>
        <ErrorBanner error={error} onRetry={() => void fetchDetail()} />
      </div>
    )
  }

  if (loading || !detail) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-8">
        <Link to="/" className="mb-4 inline-block text-sm text-brand-dark hover:underline">
          ← Back to queue
        </Link>
        <DetailSkeleton />
      </div>
    )
  }

  const { customer } = detail

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <Link to="/" className="mb-4 inline-block text-sm font-medium text-brand-dark hover:underline">
        ← Back to queue
      </Link>

      <section className="relative overflow-hidden rounded-2xl shadow-sm">
        <img
          src="/assets/practices/apex-dental-exterior.jpg"
          alt=""
          className="absolute inset-0 h-full w-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-r from-slate-900/85 via-slate-900/60 to-slate-900/20" />
        <div className="relative flex flex-wrap items-end justify-between gap-4 p-6 sm:p-8">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              {detail.in_queue && detail.rank !== null && (
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/95 text-sm font-bold text-slate-900">
                  #{detail.rank}
                </span>
              )}
              {detail.tier && <TierPill tier={detail.tier} />}
              <span
                className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                  customer.status === "prospect"
                    ? "border border-white/40 bg-white/10 text-white"
                    : "bg-white/20 text-white"
                }`}
              >
                {customer.status === "prospect" ? "Prospect" : "Customer"}
              </span>
              {detail.pinned && <span title="Pinned" className="text-lg text-amber-400">★</span>}
            </div>
            <h1 className="mt-2 text-2xl font-bold text-white sm:text-3xl">{customer.name}</h1>
            <p className="mt-1 text-sm text-slate-300">
              {detail.days_since_contact === null
                ? "Never contacted"
                : `${detail.days_since_contact}d since last contact`}
              {" · "}customer since {customer.created_at}
            </p>
          </div>
          {detail.snoozed_until && (
            <span className="rounded-full bg-white/15 px-3 py-1 text-xs font-medium text-white ring-1 ring-inset ring-white/30">
              Snoozed until {detail.snoozed_until}
            </span>
          )}
        </div>
      </section>

      {!detail.in_queue && (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-5 py-4">
          <p className="text-sm font-medium text-amber-800">
            Not in this month's queue — no activity this month.
          </p>
          {detail.kept_open ? (
            <button
              type="button"
              onClick={() => void runAction("release", undefined, "Released")}
              className="rounded-lg border border-amber-300 px-3 py-1.5 text-sm font-semibold text-amber-800 hover:bg-amber-100"
            >
              Release (undo keep open)
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void runAction("keep_open", undefined, "Keeping open — re-ranking")}
              className="rounded-lg bg-amber-500 px-3 py-1.5 text-sm font-semibold text-white shadow-sm hover:bg-amber-600"
            >
              Keep open
            </button>
          )}
        </div>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {detail.in_queue && (
            <div className="grid gap-6 sm:grid-cols-2">
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Summary
                </h2>
                <p className="mt-2 text-sm leading-relaxed text-slate-600">{detail.summary}</p>
              </div>
              <div className="rounded-xl border border-brand/30 bg-brand/5 p-5 shadow-sm">
                <h2 className="text-xs font-semibold uppercase tracking-wide text-brand-dark">
                  Suggested next step
                </h2>
                <p className="mt-2 text-sm font-medium leading-relaxed text-slate-800">
                  {detail.suggested_action}
                </p>
                {detail.reason && (
                  <p className="mt-2 text-xs leading-relaxed text-slate-500">Why: {detail.reason}</p>
                )}
              </div>
            </div>
          )}

          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Timeline · {detail.interactions.length} interactions
            </h2>
            {detail.interactions.length === 0 ? (
              <p className="text-sm text-slate-500">No interactions logged yet.</p>
            ) : (
              <ul className="-mb-1">
                {detail.interactions.map((i) => (
                  <TimelineItem key={i.id} interaction={i} />
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Quick actions
            </h2>
            <div className="flex flex-col gap-2">
              <button
                type="button"
                onClick={() => setLogOpen(true)}
                className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-dark"
              >
                + Log interaction
              </button>
              <button
                type="button"
                onClick={() => setDraftOpen(true)}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-brand hover:text-brand-dark"
              >
                ✉ Draft follow-up
              </button>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() =>
                    void runAction(
                      detail.pinned ? "unpin" : "pin",
                      undefined,
                      detail.pinned ? "Unpinned — re-ranking" : "Pinned — re-ranking",
                    )
                  }
                  className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
                    detail.pinned
                      ? "bg-amber-100 text-amber-700 hover:bg-amber-200"
                      : "border border-slate-300 text-slate-600 hover:border-brand hover:text-brand-dark"
                  }`}
                >
                  {detail.pinned ? "★ Pinned" : "☆ Pin"}
                </button>
                <div className="relative flex-1">
                  <button
                    type="button"
                    onClick={() => setSnoozeOpen((v) => !v)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-600 transition hover:border-brand hover:text-brand-dark"
                  >
                    💤 Snooze
                  </button>
                  {snoozeOpen && (
                    <div className="absolute right-0 z-10 mt-1 w-36 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg">
                      {SNOOZE_OPTIONS.map((opt) => (
                        <button
                          key={opt.days}
                          type="button"
                          onClick={() => {
                            setSnoozeOpen(false)
                            void runAction(
                              "snooze",
                              isoInDays(opt.days),
                              `Snoozed until ${isoInDays(opt.days)}`,
                              true,
                            )
                          }}
                          className="block w-full px-4 py-2 text-left text-sm text-slate-600 hover:bg-slate-50"
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              {detail.done ? (
                <button
                  type="button"
                  onClick={() => void runAction("undo", undefined, "Un-done")}
                  className="rounded-lg border border-emerald-300 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-700 hover:bg-emerald-100"
                >
                  ✓ Done — Undo
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => void runAction("done", undefined, "Marked done", true)}
                  className="rounded-lg border border-emerald-300 px-4 py-2 text-sm font-semibold text-emerald-700 transition hover:bg-emerald-50"
                >
                  ✓ Mark done
                </button>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Contacts
            </h2>
            <ul className="space-y-3">
              {detail.contacts.map((c) => (
                <li key={c.id}>
                  <p className="text-sm font-medium text-slate-800">{c.name}</p>
                  <p className="text-xs text-slate-500">
                    {c.role} · {c.email}
                  </p>
                </li>
              ))}
              {detail.contacts.length === 0 && (
                <li className="text-sm text-slate-500">No contacts.</li>
              )}
            </ul>
          </div>
        </div>
      </div>

      {logOpen && (
        <LogModal
          customerId={customer.id}
          accountName={customer.name}
          contacts={detail.contacts}
          onClose={() => setLogOpen(false)}
          onLogged={() => void fetchDetail()}
          showToast={showToast}
        />
      )}
      {draftOpen && (
        <DraftModal
          customerId={customer.id}
          accountName={customer.name}
          onClose={() => setDraftOpen(false)}
        />
      )}
    </div>
  )
}
