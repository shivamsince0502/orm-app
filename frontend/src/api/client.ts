import type {
  AccountDetail,
  ActionType,
  AccountsResponse,
  ActionResponse,
  DraftResponse,
  HealthResponse,
  InteractionCreateResponse,
  LogInteractionPayload,
  MeResponse,
  RequestOtpResponse,
  SendEmailResponse,
  Tone,
} from "../types"

export class ApiError extends Error {
  status: number
  detail?: string

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

export function errorMessage(err: unknown, fallback = "Something went wrong"): string {
  if (err instanceof ApiError && err.detail) return err.detail
  return fallback
}

function messageFromBody(status: number, body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === "string") return detail
  }
  // DRF field errors: {"field": ["msg"]} -> "field: msg"
  if (body && typeof body === "object") {
    const parts: string[] = []
    for (const [field, errors] of Object.entries(body as Record<string, unknown>)) {
      if (Array.isArray(errors)) parts.push(`${field}: ${errors.join(" ")}`)
      else if (typeof errors === "string") parts.push(`${field}: ${errors}`)
    }
    if (parts.length) return parts.join(" · ")
  }
  return `Request failed (${status})`
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  const isForm = init?.body instanceof FormData
  try {
    response = await fetch(path, {
      credentials: "same-origin",
      ...init,
      headers: isForm ? init?.headers : { "Content-Type": "application/json", ...init?.headers },
    })
  } catch {
    throw new ApiError(0, "Cannot reach the server — is the backend running?")
  }
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    /* empty body */
  }
  if (!response.ok) {
    // Expired session → back to login (auth endpoints excluded to avoid loops).
    if (response.status === 401 && !path.startsWith("/api/auth/")) {
      window.location.assign("/login")
    }
    throw new ApiError(response.status, messageFromBody(response.status, body))
  }
  return body as T
}

export function getAccounts(status?: string): Promise<AccountsResponse> {
  const query = status ? `?status=${encodeURIComponent(status)}` : ""
  return req<AccountsResponse>(`/api/accounts/${query}`)
}

export function getAccount(id: string): Promise<AccountDetail> {
  return req<AccountDetail>(`/api/accounts/${encodeURIComponent(id)}/`)
}

export function logInteraction(
  id: string,
  payload: LogInteractionPayload,
): Promise<InteractionCreateResponse> {
  return req<InteractionCreateResponse>(`/api/accounts/${encodeURIComponent(id)}/interactions/`, {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function draftFollowUp(
  id: string,
  tone?: Tone,
  prompt?: string,
): Promise<DraftResponse> {
  return req<DraftResponse>(`/api/accounts/${encodeURIComponent(id)}/draft/`, {
    method: "POST",
    body: JSON.stringify({
      ...(tone ? { tone } : {}),
      ...(prompt && prompt.trim() ? { prompt: prompt.trim() } : {}),
    }),
  })
}

export function postAction(
  id: string,
  action: ActionType,
  snoozeUntil?: string,
): Promise<ActionResponse> {
  return req<ActionResponse>(`/api/accounts/${encodeURIComponent(id)}/actions/`, {
    method: "POST",
    body: JSON.stringify(snoozeUntil ? { action, snooze_until: snoozeUntil } : { action }),
  })
}

export function getHealth(): Promise<HealthResponse> {
  return req<HealthResponse>("/api/health/")
}

export function requestOtp(email: string): Promise<RequestOtpResponse> {
  return req<RequestOtpResponse>("/api/auth/request-otp/", {
    method: "POST",
    body: JSON.stringify({ email }),
  })
}

export function verifyOtp(email: string, code: string): Promise<MeResponse> {
  return req<MeResponse>("/api/auth/verify-otp/", {
    method: "POST",
    body: JSON.stringify({ email, code }),
  })
}

export function getMe(): Promise<MeResponse> {
  return req<MeResponse>("/api/auth/me/")
}

export function logout(): Promise<{ ok: boolean }> {
  return req<{ ok: boolean }>("/api/auth/logout/", { method: "POST" })
}

export function sendFollowUpEmail(
  id: string,
  payload: { contact_id: string; subject: string; body: string },
  files?: File[],
): Promise<SendEmailResponse> {
  const form = new FormData()
  form.append("contact_id", payload.contact_id)
  form.append("subject", payload.subject)
  form.append("body", payload.body)
  for (const file of files ?? []) form.append("attachments", file, file.name)
  return req<SendEmailResponse>(`/api/accounts/${encodeURIComponent(id)}/send-email/`, {
    method: "POST",
    body: form,
  })
}
