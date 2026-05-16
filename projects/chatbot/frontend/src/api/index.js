function getApiBase() {
  const baseUrl = import.meta.env.BASE_URL || '/'
  return baseUrl.replace(/\/$/, '')
}

export async function apiLogin(username, password) {
  const res = await fetch(`${getApiBase()}/api/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Login failed' }))
    throw new Error(err.detail || 'Login failed')
  }
  return res.json()
}

export async function apiRegister(username, password) {
  const res = await fetch(`${getApiBase()}/api/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Register failed' }))
    throw new Error(err.detail || 'Register failed')
  }
  return res.json()
}

export async function apiDeleteSession(token, chatId) {
  const res = await fetch(`${getApiBase()}/api/session/${chatId}`, {
    method: 'DELETE',
    headers: { 'Authorization': `Bearer ${token}` }
  })
  if (!res.ok) throw new Error('Failed to delete session')
  return res.json()
}

export async function apiListSessions(token) {
  const res = await fetch(`${getApiBase()}/api/sessions`, {
    headers: { 'Authorization': `Bearer ${token}` }
  })
  if (!res.ok) throw new Error('Failed to list sessions')
  return res.json()
}

export async function apiGetHistory(token, limit = 100, chatId) {
  const res = await fetch(`${getApiBase()}/api/history?limit=${limit}&chat_id=${encodeURIComponent(chatId)}`, {
    headers: { 'Authorization': `Bearer ${token}` }
  })
  if (!res.ok) throw new Error('Failed to fetch history')
  return res.json()
}

export function parseServerTimestamp(value) {
  if (!value) return new Date().toISOString()
  if (typeof value === 'number') {
    return new Date(value * (value > 1e12 ? 1 : 1000)).toISOString()
  }
  if (typeof value === 'string') {
    const num = Number(value)
    if (!isNaN(num)) {
      return new Date(num > 1e12 ? num : num * 1000).toISOString()
    }
    return new Date(value).toISOString()
  }
  return new Date().toISOString()
}

export function parseHistoryToMessages(data) {
  if (!data.history || data.history.length === 0) return []

  return data.history.map((h) => ({
    role: h.role,
    content: h.content || '',
    thinking: h.thinking || '',
    thinkingCompleted: h.thinking_completed ?? (!!h.thinking && h.thinking.length > 0),
    tool_calls: h.tool_calls?.map(tc => tc.name) || [],
    tool_traces: (h.tool_calls || []).map((tc, i) => ({
      tool_call_id: tc.call_id || `call_${i}`,
      tool_name: tc.name || 'unknown_tool',
      arguments: tc.arguments || null,
      result: tc.result || null,
      status: tc.status || 'completed'
    })),
    usage: h.usage || null,
    timestamp: parseServerTimestamp(h.created_at),
    serverId: h.id || null
  }))
}