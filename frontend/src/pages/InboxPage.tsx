import { useCallback, useEffect, useMemo, useState } from "react"
import AccountCard from "../components/AccountCard"
import DraftModal from "../components/DraftModal"
import ErrorBanner from "../components/ErrorBanner"
import { InboxSkeleton } from "../components/Skeleton"
import { useToast } from "../components/Toast"
import { errorMessage, getAccounts, postAction } from "../api/client"
import { timeAgo } from "../lib/format"
import type { QueueItem } from "../types"

type Tab = "all" | "prospect" | "customer"
type SortMode = "rank" | "days"

const TABS: { value: Tab; label: string }[] = [
  { value: "all", label: "All" },
  { value: "prospect", label: "Prospects" },
  { value: "customer", label: "Customers" },
]

export default function InboxPage() {
  const { showToast } = useToast()
  const [data, setData] = useState<Awaited<ReturnType<typeof getAccounts>> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)
  const [tab, setTab] = useState<Tab>("all")
  const [search, setSearch] = useState("")
  const [sortMode, setSortMode] = useState<SortMode>("rank")
  const [optimisticHidden, setOptimisticHidden] = useState<Set<string>>(new Set())
  const [pinOverrides, setPinOverrides] = useState<Record<string, boolean>>({})
  const [keepingOpen, setKeepingOpen] = useState<Set<string>>(new Set())
  const [outExpanded, setOutExpanded] = useState(false)
  const [draftFor, setDraftFor] = useState<QueueItem | null>(null)

  const fetchAccounts = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await getAccounts(tab === "all" ? undefined : tab)
      setData(result)
      setOptimisticHidden(new Set())
      setPinOverrides({})
      setKeepingOpen(new Set())
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [tab])

  useEffect(() => {
    void fetchAccounts()
  }, [fetchAccounts])

  const hide = (id: string) =>
    setOptimisticHidden((prev) => {
      const next = new Set(prev)
      next.add(id)
      return next
    })

  const unhide = (id: string) =>
    setOptimisticHidden((prev) => {
      const next = new Set(prev)
      next.delete(id)
      return next
    })

  const handleDone = async (item: QueueItem) => {
    hide(item.id)
    try {
      await postAction(item.id, "done")
      showToast("Marked done", {
        label: "Undo",
        onClick: () => {
          void (async () => {
            try {
              await postAction(item.id, "undo")
            } finally {
              unhide(item.id)
              void fetchAccounts()
            }
          })()
        },
      })
    } catch (err) {
      unhide(item.id)
      showToast(errorMessage(err, "Action failed"))
    }
  }

  const handleSnooze = async (item: QueueItem, snoozeUntil: string) => {
    hide(item.id)
    try {
      await postAction(item.id, "snooze", snoozeUntil)
      showToast(`Snoozed until ${snoozeUntil}`, {
        label: "Undo",
        onClick: () => {
          void (async () => {
            try {
              await postAction(item.id, "undo")
            } finally {
              unhide(item.id)
              void fetchAccounts()
            }
          })()
        },
      })
    } catch (err) {
      unhide(item.id)
      showToast(errorMessage(err, "Action failed"))
    }
  }

  const handlePinToggle = async (item: QueueItem, nextPinned: boolean) => {
    setPinOverrides((prev) => ({ ...prev, [item.id]: nextPinned }))
    try {
      await postAction(item.id, nextPinned ? "pin" : "unpin")
      showToast(nextPinned ? "Pinned — re-ranking queue" : "Unpinned — re-ranking queue")
      await fetchAccounts() // pin/unpin invalidates → blocking re-rank with skeletons (D6)
    } catch (err) {
      setPinOverrides((prev) => ({ ...prev, [item.id]: !nextPinned }))
      showToast(errorMessage(err, "Action failed"))
    }
  }

  const handleKeepOpen = async (id: string) => {
    setKeepingOpen((prev) => new Set(prev).add(id))
    try {
      await postAction(id, "keep_open")
      showToast("Keeping open — re-ranking queue")
      await fetchAccounts()
    } catch (err) {
      setKeepingOpen((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
      showToast(errorMessage(err, "Action failed"))
    }
  }

  const effectiveQueue = useMemo(() => {
    if (!data) return []
    return data.queue
      .filter((item) => !item.hidden && !optimisticHidden.has(item.id))
      .map((item) =>
        pinOverrides[item.id] === undefined ? item : { ...item, pinned: pinOverrides[item.id] },
      )
      .filter((item) => {
        if (!search.trim()) return true
        const q = search.trim().toLowerCase()
        return (
          item.name.toLowerCase().includes(q) ||
          item.contact_names.some((n) => n.toLowerCase().includes(q))
        )
      })
      .sort((a, b) => {
        if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
        if (sortMode === "days") {
          const av = a.days_since_contact ?? Number.MAX_SAFE_INTEGER
          const bv = b.days_since_contact ?? Number.MAX_SAFE_INTEGER
          return av - bv
        }
        return a.rank - b.rank
      })
  }, [data, optimisticHidden, pinOverrides, search, sortMode])

  const kpis = useMemo(() => {
    if (!data) return null
    const visible = data.queue.filter((item) => !item.hidden && !optimisticHidden.has(item.id))
    return {
      high: visible.filter((i) => i.tier === "high").length,
      medium: visible.filter((i) => i.tier === "medium").length,
      out: data.out_of_queue.length,
      asOf: timeAgo(data.as_of),
    }
  }, [data, optimisticHidden])

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Follow-Up Queue</h1>
          {kpis && (
            <p className="mt-1 text-sm text-slate-500">
              {kpis.high} high · {kpis.medium} medium · {kpis.out} out of queue · ranked{" "}
              {kpis.asOf || "—"}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search accounts or contacts…"
            className="w-56 rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
          />
          <div className="flex rounded-lg border border-slate-300 bg-white p-0.5 shadow-sm">
            {(
              [
                { value: "rank", label: "Rank" },
                { value: "days", label: "Days since" },
              ] as { value: SortMode; label: string }[]
            ).map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setSortMode(opt.value)}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                  sortMode === opt.value
                    ? "bg-slate-900 text-white"
                    : "text-slate-500 hover:text-slate-800"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="mb-6 flex gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t.value}
            type="button"
            onClick={() => setTab(t.value)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition ${
              tab === t.value
                ? "border-brand text-brand-dark"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error ? (
        <ErrorBanner error={error} onRetry={() => void fetchAccounts()} />
      ) : loading ? (
        <InboxSkeleton rows={5} />
      ) : (
        <>
          {effectiveQueue.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-300 bg-white p-12 text-center">
              <p className="text-lg font-semibold text-slate-700">All caught up</p>
              <p className="mt-1 text-sm text-slate-500">
                No accounts need attention right now. Done and snoozed accounts are hidden.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {effectiveQueue.map((item) => (
                <AccountCard
                  key={item.id}
                  item={item}
                  onDone={(i) => void handleDone(i)}
                  onSnooze={(i, until) => void handleSnooze(i, until)}
                  onPinToggle={(i, next) => void handlePinToggle(i, next)}
                  onDraft={(i) => setDraftFor(i)}
                />
              ))}
            </div>
          )}

          {data && data.out_of_queue.length > 0 && (
            <div className="mt-8">
              <button
                type="button"
                onClick={() => setOutExpanded((v) => !v)}
                className="flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-5 py-3.5 text-left shadow-sm transition hover:bg-slate-50"
              >
                <span className="text-sm font-semibold text-slate-600">
                  Out of queue ({data.out_of_queue.length})
                </span>
                <span className="text-xs text-slate-400">
                  No activity this month · {outExpanded ? "Hide" : "Show"}
                </span>
              </button>
              {outExpanded && (
                <ul className="mt-3 divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white shadow-sm">
                  {data.out_of_queue.map((row) => (
                    <li
                      key={row.id}
                      className="flex flex-wrap items-center gap-x-3 gap-y-1 px-5 py-3"
                    >
                      <a
                        href={`/accounts/${row.id}`}
                        className="text-sm font-medium text-slate-800 hover:text-brand-dark hover:underline"
                      >
                        {row.name}
                      </a>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          row.status === "prospect"
                            ? "border border-brand/40 bg-brand/5 text-brand-dark"
                            : "bg-slate-100 text-slate-600"
                        }`}
                      >
                        {row.status === "prospect" ? "Prospect" : "Customer"}
                      </span>
                      <span className="text-xs text-slate-400">
                        {row.days_since_contact === null
                          ? "Never contacted"
                          : `${row.days_since_contact}d since last contact`}
                      </span>
                      {keepingOpen.has(row.id) || row.kept_open ? (
                        <span className="ml-auto rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-600 ring-1 ring-inset ring-indigo-200">
                          Keeping open…
                        </span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => void handleKeepOpen(row.id)}
                          className="ml-auto rounded-lg border border-slate-300 px-3 py-1 text-xs font-semibold text-slate-600 transition hover:border-brand hover:text-brand-dark"
                        >
                          Keep open
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}

      {draftFor && (
        <DraftModal
          customerId={draftFor.id}
          accountName={draftFor.name}
          onClose={() => setDraftFor(null)}
        />
      )}
    </div>
  )
}
