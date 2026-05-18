function getApiBase() {
  const baseUrl = import.meta.env.BASE_URL || '/'
  return baseUrl.replace(/\/$/, '')
}

class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function parseErrorResponse(res, fallback) {
  const err = await res.json().catch(() => ({ detail: fallback }))
  return new ApiError(err.detail || fallback, res.status)
}

export async function apiLogin(username, password) {
  const res = await fetch(`${getApiBase()}/api/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  })
  if (!res.ok) {
    throw await parseErrorResponse(res, 'Login failed')
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
    throw await parseErrorResponse(res, 'Register failed')
  }
  return res.json()
}

export async function apiDeleteSession(token, chatId) {
  const res = await fetch(`${getApiBase()}/api/session/${chatId}`, {
    method: 'DELETE',
    headers: { 'Authorization': `Bearer ${token}` }
  })
  if (!res.ok) throw await parseErrorResponse(res, 'Failed to delete session')
  return res.json()
}

export async function apiListSessions(token) {
  const res = await fetch(`${getApiBase()}/api/sessions`, {
    headers: { 'Authorization': `Bearer ${token}` }
  })
  if (!res.ok) throw await parseErrorResponse(res, 'Failed to list sessions')
  return res.json()
}

export async function apiGetHistory(token, limit = 100, chatId) {
  const res = await fetch(`${getApiBase()}/api/history?limit=${limit}&chat_id=${encodeURIComponent(chatId)}`, {
    headers: { 'Authorization': `Bearer ${token}` }
  })
  if (!res.ok) throw await parseErrorResponse(res, 'Failed to fetch history')
  return res.json()
}

export async function apiUploadUserFile(token, file, maxTextLength = 12000) {
  const form = new FormData()
  form.append('file', file)
  form.append('max_text_length', String(maxTextLength))

  const res = await fetch(`${getApiBase()}/api/upload`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
    body: form
  })

  if (!res.ok) {
    throw await parseErrorResponse(res, 'Upload failed')
  }

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
    attachments: (h.attachments || []).map((item) => ({
      fileName: item.file_name || item.fileName || 'uploaded_file',
      savedPath: item.saved_path || item.savedPath || '',
      size: item.size
    })).filter((item) => item.savedPath),
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