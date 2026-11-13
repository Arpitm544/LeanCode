export type AgentEvent = { id: number; kind: string; data: Record<string, unknown>; created_at: string }
export type Action = { id: string; kind: string; status: string; payload: { diff?: string; command?: string[]; reason?: string } }
export type Session = {
  id: string; repository: string; task: string; status: string; created_at: string
  state: { model?: string; input_tokens?: number; output_tokens?: number; cost_micro?: number; mode?: string }
  actions: Action[]; events: AgentEvent[]
}
export type Bootstrap = {
  repositories: { id: string; name: string; confidential: boolean }[]
  user: { id: string; limit_micro: number; spent_micro: number; reserved_micro: number }
  integrations: { name: string; configured: boolean; detail: string }[]
  sessions: Session[]
}

export async function request<T>(path: string, token: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, ...options.headers },
  })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try { message = (await response.json()).detail || message } catch { /* Empty error response. */ }
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message))
  }
  return response.json() as Promise<T>
}

export async function streamEvents(id: string, token: string, after: number, signal: AbortSignal, onEvent: (event: AgentEvent) => void) {
  const response = await fetch(`/api/sessions/${id}/events?after=${after}`, {
    headers: { Authorization: `Bearer ${token}` }, signal,
  })
  if (!response.ok || !response.body) throw new Error('Live connection interrupted')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
      let end: number
      while ((end = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, end)
        buffer = buffer.slice(end + 2)
        const data = frame.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trim()).join('\n')
        if (data) onEvent(JSON.parse(data))
      }
    }
  } finally { reader.releaseLock() }
}
