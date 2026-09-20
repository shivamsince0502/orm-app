import { useEffect, useState } from "react"
import Modal from "./Modal"
import ErrorBanner from "./ErrorBanner"
import { errorMessage, draftFollowUp, getAccount, sendFollowUpEmail } from "../api/client"
import type { Contact, DraftResponse, Tone } from "../types"

interface Props {
  customerId: string
  accountName: string
  onClose: () => void
}

const TONES: { value: Tone; label: string }[] = [
  { value: "friendly", label: "Friendly" },
  { value: "professional", label: "Professional" },
  { value: "warm", label: "Warm" },
  { value: "direct", label: "Direct" },
]

export default function DraftModal({ customerId, accountName, onClose }: Props) {
  const [tone, setTone] = useState<Tone>("professional")
  const [prompt, setPrompt] = useState("")
  const [loading, setLoading] = useState(false)
  const [draft, setDraft] = useState<DraftResponse | null>(null)
  const [subject, setSubject] = useState("")
  const [body, setBody] = useState("")
  const [error, setError] = useState<unknown>(null)
  const [copied, setCopied] = useState(false)
  const [contacts, setContacts] = useState<Contact[]>([])
  const [contactId, setContactId] = useState("")
  const [sending, setSending] = useState(false)
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [sendError, setSendError] = useState<string | null>(null)
  const [files, setFiles] = useState<File[]>([])

  const MAX_FILES = 5
  const MAX_TOTAL_MB = 10

  const addFiles = (picked: FileList | null) => {
    if (!picked?.length) return
    const next = [...files, ...Array.from(picked)]
    const totalMb = next.reduce((sum, f) => sum + f.size, 0) / (1024 * 1024)
    if (next.length > MAX_FILES) {
      setSendError(`At most ${MAX_FILES} attachments.`)
      return
    }
    if (totalMb > MAX_TOTAL_MB) {
      setSendError("Attachments exceed 10 MB total.")
      return
    }
    setSendError(null)
    setFiles(next)
  }

  // Contacts for the recipient picker (from the account detail).
  useEffect(() => {
    let cancelled = false
    getAccount(customerId)
      .then((detail) => {
        if (cancelled) return
        setContacts(detail.contacts)
        setContactId((current) => current || detail.contacts[0]?.id || "")
      })
      .catch(() => {
        /* picker stays empty — send will surface the error */
      })
    return () => {
      cancelled = true
    }
  }, [customerId])

  const generate = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await draftFollowUp(customerId, tone, prompt)
      setDraft(result)
      setSubject(result.subject)
      setBody(result.body)
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }

  const copy = async () => {
    await navigator.clipboard.writeText(`Subject: ${subject}\n\n${body}`)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 2000)
  }

  const send = async () => {
    if (!contactId) {
      setSendError("Pick a recipient.")
      return
    }
    setSending(true)
    setSendError(null)
    try {
      const result = await sendFollowUpEmail(
        customerId,
        { contact_id: contactId, subject, body },
        files,
      )
      setSentTo(result.to)
      setFiles([])
    } catch (err) {
      setSendError(errorMessage(err, "Email send failed."))
    } finally {
      setSending(false)
    }
  }

  return (
    <Modal title={`AI follow-up draft — ${accountName}`} onClose={onClose}>
      {error ? (
        <ErrorBanner error={error} onRetry={() => void generate()} />
      ) : draft === null ? (
        <div className="space-y-5">
          <p className="text-sm text-slate-600">
            Generate a follow-up email grounded in this account's interaction history. Pick a tone,
            optionally add your own instructions, then generate.
          </p>
          <div>
            <span className="mb-2 block text-sm font-medium text-slate-700">Tone</span>
            <div className="flex flex-wrap gap-2">
              {TONES.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => setTone(t.value)}
                  className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
                    tone === t.value
                      ? "bg-brand text-white shadow-sm"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">
              Your instructions <span className="font-normal text-slate-400">(optional)</span>
            </span>
            <textarea
              rows={2}
              maxLength={500}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g. Mention the free trial, ask about their September planning meeting…"
              className="w-full resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
            />
            <span className="mt-1 block text-right text-xs text-slate-400">{prompt.length}/500</span>
          </label>
          <button
            type="button"
            disabled={loading}
            onClick={() => void generate()}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-dark disabled:opacity-60"
          >
            {loading && (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
            )}
            {loading ? "Drafting… (up to 30s)" : "Generate draft"}
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">Subject</span>
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">Body</span>
            <textarea
              rows={10}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm leading-relaxed focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
            />
          </label>

          {sentTo ? (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">
              Sent to {sentTo}
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={contactId}
                onChange={(e) => setContactId(e.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
              >
                {contacts.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.role}) — {c.email}
                  </option>
                ))}
              </select>
              <button
                type="button"
                disabled={sending || !contactId || !subject.trim() || !body.trim()}
                onClick={() => void send()}
                className="rounded-lg bg-brand-dark px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-brand disabled:opacity-60"
              >
                {sending ? "Sending…" : "Send email"}
              </button>
            </div>
          )}
          {sendError && <p className="text-sm font-medium text-red-600">{sendError}</p>}

          <div>
            <div className="flex items-center gap-2">
              <label className="cursor-pointer rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 transition hover:border-brand hover:text-brand-dark">
                📎 Attach files (max {MAX_FILES}, {MAX_TOTAL_MB}MB)
                <input
                  type="file"
                  multiple
                  className="hidden"
                  onChange={(e) => {
                    addFiles(e.target.files)
                    e.target.value = ""
                  }}
                />
              </label>
            </div>
            {files.length > 0 && (
              <ul className="mt-2 space-y-1">
                {files.map((file, i) => (
                  <li
                    key={`${file.name}-${i}`}
                    className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-1.5 text-sm text-slate-600"
                  >
                    <span className="truncate">{file.name}</span>
                    <span className="text-xs text-slate-400">
                      {(file.size / 1024).toFixed(0)} KB
                    </span>
                    <button
                      type="button"
                      onClick={() => setFiles(files.filter((_, j) => j !== i))}
                      className="ml-auto text-slate-400 transition hover:text-red-500"
                      aria-label={`Remove ${file.name}`}
                    >
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void copy()}
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-brand hover:text-brand-dark"
            >
              {copied ? "Copied!" : "Copy"}
            </button>
            <button
              type="button"
              onClick={() => {
                setDraft(null)
                setSubject("")
                setBody("")
                setSentTo(null)
                setSendError(null)
                setFiles([])
              }}
              className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
            >
              Start over
            </button>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Grounded in {draft.grounded_sources.length} interactions
            </p>
            <ul className="mt-2 space-y-1.5">
              {draft.grounded_sources.map((s) => (
                <li key={s.id} className="flex gap-2 text-xs text-slate-500">
                  <span className="font-medium capitalize text-slate-600">{s.type}</span>
                  <span>{s.occurred_at}</span>
                  <span className="truncate">— {s.excerpt}…</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </Modal>
  )
}
