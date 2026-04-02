import type { PipelineEvent } from '../types/api'

const BASE = ''

export async function apiGet<T>(url: string): Promise<T> {
  const res = await fetch(`${BASE}${url}`)
  if (!res.ok) throw new Error(`GET ${url}: ${res.status}`)
  return res.json()
}

export async function apiPost<T>(url: string, body?: any): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`POST ${url}: ${res.status}`)
  return res.json()
}

export async function apiPut<T>(url: string, body: any): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`PUT ${url}: ${res.status}`)
  return res.json()
}

export async function apiDelete<T>(url: string): Promise<T> {
  const res = await fetch(`${BASE}${url}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`DELETE ${url}: ${res.status}`)
  return res.json()
}

export async function streamSSE(
  url: string,
  body: any,
  onEvent: (event: PipelineEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  console.log(`[SSE] POST ${BASE}${url}`, body)
  const res = await fetch(`${BASE}${url}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })

  console.log(`[SSE] Response status: ${res.status}`)
  if (!res.ok) throw new Error(`SSE ${url}: ${res.status}`)
  if (!res.body) throw new Error('No response body')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed || !trimmed.startsWith('data: ')) continue
      try {
        const event = JSON.parse(trimmed.substring(6)) as PipelineEvent
        onEvent(event)
      } catch {
        // skip parse errors
      }
    }
  }
}
