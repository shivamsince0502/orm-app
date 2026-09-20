import type { Tier } from "../types"

const STYLES: Record<Tier, { label: string; className: string }> = {
  high: {
    label: "High",
    className: "bg-red-50 text-red-600 ring-red-200",
  },
  medium: {
    label: "Medium",
    className: "bg-amber-50 text-amber-600 ring-amber-200",
  },
  low: {
    label: "Low",
    className: "bg-slate-100 text-slate-500 ring-slate-200",
  },
}

export default function TierPill({ tier }: { tier: Tier }) {
  const style = STYLES[tier]
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide ring-1 ring-inset ${style.className}`}
    >
      {style.label}
    </span>
  )
}
