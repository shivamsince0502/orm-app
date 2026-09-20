import { useState } from "react"
import { useNavigate } from "react-router-dom"
import TierPill from "./TierPill"
import type { QueueItem } from "../types"

interface Props {
  item: QueueItem
  onDone: (item: QueueItem) => void
  onSnooze: (item: QueueItem, snoozeUntil: string) => void
  onPinToggle: (item: QueueItem, nextPinned: boolean) => void
  onDraft: (item: QueueItem) => void
}

function snoozeOptions(): { label: string; days: number }[] {
  return [
    { label: "Tomorrow", days: 1 },
    { label: "3 days", days: 3 },
    { label: "1 week", days: 7 },
  ]
}

function isoInDays(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

function StatusChip({ status }: { status: QueueItem["status"] }) {
  if (status === "prospect") {
    return (
      <span className="inline-flex items-center rounded-full border border-brand/40 bg-brand/5 px-2 py-0.5 text-xs font-medium text-brand-dark">
        Prospect
      </span>
    )
  }
  return (
    <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
      Customer
    </span>
  )
}

export default function AccountCard({ item, onDone, onSnooze, onPinToggle, onDraft }: Props) {
  const navigate = useNavigate()
  const [snoozeOpen, setSnoozeOpen] = useState(false)

  const goToDetail = () => navigate(`/accounts/${item.id}`)

  return (
    <article
      onClick={goToDetail}
      className={`cursor-pointer rounded-xl border bg-white p-5 shadow-sm transition hover:shadow-md ${
        item.pinned ? "border-brand/50 ring-1 ring-brand/20" : "border-slate-200"
      }`}
    >
      <div className="flex items-start gap-3">
        <span
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-sm font-bold text-white"
          title={`Rank #${item.rank}`}
        >
          #{item.rank}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-base font-semibold text-slate-900">{item.name}</h3>
            <TierPill tier={item.tier} />
            <StatusChip status={item.status} />
            {item.kept_open && (
              <span className="inline-flex items-center rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-600 ring-1 ring-inset ring-indigo-200">
                Kept open
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs text-slate-400">
            {item.contact_names.length > 0 ? item.contact_names.join(" · ") : "No contacts"}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-sm font-semibold text-slate-700">
            {item.days_since_contact === null
              ? "Never contacted"
              : `${item.days_since_contact}d since last contact`}
          </p>
        </div>
      </div>

      <div className="mt-4 space-y-1.5">
        <p className="text-sm leading-relaxed text-slate-600">
          <span className="font-medium text-slate-700">Why now: </span>
          {item.reason}
        </p>
        <p className="text-sm leading-relaxed text-slate-600">
          <span className="font-medium text-slate-700">Next step: </span>
          {item.suggested_action}
        </p>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          onClick={() => onPinToggle(item, !item.pinned)}
          title={item.pinned ? "Unpin" : "Pin to top"}
          className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-medium transition ${
            item.pinned
              ? "bg-amber-100 text-amber-700 hover:bg-amber-200"
              : "text-slate-500 hover:bg-slate-100 hover:text-slate-700"
          }`}
        >
          <span aria-hidden>{item.pinned ? "★" : "☆"}</span>
          {item.pinned ? "Pinned" : "Pin"}
        </button>
        <button
          type="button"
          onClick={() => setSnoozeOpen((v) => !v)}
          className="inline-flex items-center rounded-lg px-2.5 py-1.5 text-sm font-medium text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
        >
          💤 Snooze
        </button>
        {snoozeOpen && (
          <div className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 p-1">
            {snoozeOptions().map((opt) => (
              <button
                key={opt.days}
                type="button"
                onClick={() => {
                  setSnoozeOpen(false)
                  onSnooze(item, isoInDays(opt.days))
                }}
                className="rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-white hover:text-slate-900"
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
        <button
          type="button"
          onClick={() => onDone(item)}
          className="inline-flex items-center rounded-lg px-2.5 py-1.5 text-sm font-medium text-emerald-700 transition hover:bg-emerald-50"
        >
          ✓ Done
        </button>
        <button
          type="button"
          onClick={() => onDraft(item)}
          className="ml-auto inline-flex items-center gap-1.5 rounded-lg bg-brand px-3 py-1.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-dark"
        >
          ✉ Draft
        </button>
      </div>
    </article>
  )
}
