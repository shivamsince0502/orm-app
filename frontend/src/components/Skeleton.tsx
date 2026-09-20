export function CardSkeleton() {
  return (
    <div className="animate-pulse rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-3">
        <div className="h-8 w-8 rounded-lg bg-slate-200" />
        <div className="h-5 w-1/3 rounded bg-slate-200" />
        <div className="ml-auto h-5 w-16 rounded-full bg-slate-200" />
      </div>
      <div className="mt-4 h-4 w-3/4 rounded bg-slate-100" />
      <div className="mt-2 h-4 w-1/2 rounded bg-slate-100" />
      <div className="mt-5 flex gap-2">
        <div className="h-8 w-16 rounded-lg bg-slate-100" />
        <div className="h-8 w-16 rounded-lg bg-slate-100" />
        <div className="h-8 w-16 rounded-lg bg-slate-100" />
      </div>
    </div>
  )
}

export function InboxSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-4" aria-label="Loading queue">
      {Array.from({ length: rows }).map((_, i) => (
        <CardSkeleton key={i} />
      ))}
    </div>
  )
}

export function SectionSkeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl bg-slate-200/70 ${className}`} />
}

export default function DetailSkeleton() {
  return (
    <div className="space-y-6" aria-label="Loading account">
      <SectionSkeleton className="h-44 w-full" />
      <div className="grid gap-6 lg:grid-cols-3">
        <SectionSkeleton className="h-40 lg:col-span-2" />
        <SectionSkeleton className="h-40" />
      </div>
      <SectionSkeleton className="h-64 w-full" />
    </div>
  )
}
