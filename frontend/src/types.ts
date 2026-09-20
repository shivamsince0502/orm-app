export type Tier = "high" | "medium" | "low"
export type Status = "prospect" | "customer"
export type ActionType =
  | "done"
  | "undo"
  | "snooze"
  | "pin"
  | "unpin"
  | "keep_open"
  | "release"
export type Tone = "friendly" | "professional" | "warm" | "direct"

export interface QueueItem {
  id: string
  name: string
  status: Status
  rank: number
  tier: Tier
  reason: string
  suggested_action: string
  days_since_contact: number | null
  hidden: boolean
  pinned: boolean
  kept_open: boolean
  contact_names: string[]
}

export interface OutOfQueueItem {
  id: string
  name: string
  status: Status
  days_since_contact: number | null
  kept_open: boolean
}

export interface AccountsResponse {
  as_of: string
  queue: QueueItem[]
  out_of_queue: OutOfQueueItem[]
}

export interface Contact {
  id: string
  name: string
  email: string
  role: string
}

export interface TimelineInteraction {
  id: string
  type: "email" | "call" | "meeting" | "note"
  occurred_at: string
  notes: string
  contact: { id: string; name: string; role: string }
}

export interface AccountDetail {
  customer: { id: string; name: string; status: Status; created_at: string }
  in_queue: boolean
  rank: number | null
  tier: Tier | null
  reason: string | null
  suggested_action: string | null
  summary: string | null
  days_since_contact: number | null
  pinned: boolean
  kept_open: boolean
  done: boolean
  snoozed_until: string | null
  contacts: Contact[]
  interactions: TimelineInteraction[]
}

export interface LogInteractionPayload {
  type: TimelineInteraction["type"]
  contact_id: string
  occurred_at: string
  notes: string
}

export interface InteractionCreateResponse {
  interaction: TimelineInteraction
  days_since_contact: number | null
  rerank_pending: boolean
}

export interface GroundedSource {
  id: string
  type: string
  occurred_at: string
  excerpt: string
}

export interface DraftResponse {
  subject: string
  body: string
  grounded_sources: GroundedSource[]
}

export interface ActionResponse {
  done: boolean
  snoozed_until: string | null
  pinned: boolean
  kept_open: boolean
}

export interface HealthResponse {
  ok: boolean
  llm: boolean
}

export interface MeResponse {
  email: string
}

export interface RequestOtpResponse {
  sent: boolean
  cooldown_seconds: number
}

export interface SendEmailResponse {
  sent: boolean
  to: string
}
