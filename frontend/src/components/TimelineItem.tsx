import type { TimelineInteraction } from "../types"

const TYPE_STYLES: Record<TimelineInteraction["type"], { label: string; className: string }> = {
  email: { label: "✉", className: "bg-sky-50 text-sky-600 ring-sky-200" },
  call: { label: "☎", className: "bg-emerald-50 text-emerald-600 ring-emerald-200" },
  meeting: { label: "👥", className: "bg-violet-50 text-violet-600 ring-violet-200" },
  note: { label: "📝", className: "bg-amber-50 text-amber-600 ring-amber-200" },
}

export default function TimelineItem({ interaction }: { interaction: TimelineInteraction }) {
  const style = TYPE_STYLES[interaction.type]
  return (
    <li className="relative flex gap-4 pb-6 last:pb-0">
      <span
        className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm ring-1 ring-inset ${style.className}`}
        title={interaction.type}
      >
        {style.label}
      </span>
      <div className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
          <span className="font-semibold text-slate-900">{interaction.contact.name}</span>
          <span className="text-slate-400">·</span>
          <span className="capitalize text-slate-500">{interaction.type}</span>
          <span className="ml-auto text-xs font-medium text-slate-400">
            {interaction.occurred_at}
          </span>
        </div>
        <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{interaction.notes}</p>
      </div>
    </li>
  )
}
