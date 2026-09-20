import { useState } from "react"
import Modal from "./Modal"
import { errorMessage, logInteraction } from "../api/client"
import type { Contact, LogInteractionPayload, TimelineInteraction } from "../types"

interface Props {
  customerId: string
  accountName: string
  contacts: Contact[]
  onClose: () => void
  onLogged: () => void
  showToast: (message: string) => void
}

const TYPES: { value: TimelineInteraction["type"]; label: string }[] = [
  { value: "email", label: "Email" },
  { value: "call", label: "Call" },
  { value: "meeting", label: "Meeting" },
  { value: "note", label: "Note" },
]

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

export default function LogModal({
  customerId,
  accountName,
  contacts,
  onClose,
  onLogged,
  showToast,
}: Props) {
  const [type, setType] = useState<TimelineInteraction["type"]>("call")
  const [contactId, setContactId] = useState(contacts[0]?.id ?? "")
  const [occurredAt, setOccurredAt] = useState(todayIso())
  const [notes, setNotes] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const submit = async () => {
    if (!contactId) {
      setError("Pick a contact.")
      return
    }
    if (!notes.trim()) {
      setError("Notes cannot be empty.")
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await logInteraction(customerId, {
        type,
        contact_id: contactId,
        occurred_at: occurredAt,
        notes: notes.trim(),
      } satisfies LogInteractionPayload)
      showToast("Logged — re-ranking queue")
      onLogged()
      onClose()
    } catch (err) {
      setError(errorMessage(err, "Could not log the interaction."))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal title={`Log interaction — ${accountName}`} onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          void submit()
        }}
      >
        <div className="grid grid-cols-2 gap-4">
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">Type</span>
            <select
              value={type}
              onChange={(e) => setType(e.target.value as TimelineInteraction["type"])}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
            >
              {TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">Contact</span>
            <select
              value={contactId}
              onChange={(e) => setContactId(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
            >
              {contacts.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.role})
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">Date</span>
          <input
            type="date"
            required
            value={occurredAt}
            max={todayIso()}
            onChange={(e) => setOccurredAt(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">Notes</span>
          <textarea
            required
            rows={4}
            value={notes}
            maxLength={2000}
            placeholder="What happened? What was discussed or agreed?"
            onChange={(e) => setNotes(e.target.value)}
            className="w-full resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
          />
          <span className="mt-1 block text-right text-xs text-slate-400">{notes.length}/2000</span>
        </label>
        {error && <p className="text-sm font-medium text-red-600">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-dark disabled:opacity-50"
          >
            {submitting ? "Saving…" : "Log interaction"}
          </button>
        </div>
      </form>
    </Modal>
  )
}
