import { memo, useState, useEffect, useRef, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { APP_CONFIG } from './appConfig'

const STORAGE_KEY = 'agentforge_chats_v3'
const AUTH_TOKEN_KEY = 'agentforge_auth_token'
const AUTH_USER_KEY = 'agentforge_auth_user'
const PERSIST_DEBOUNCE_MS = 500
const INITIAL_VISIBLE_MESSAGES = 80
const MESSAGE_PAGE_SIZE = 80
const THINKING_TYPEWRITER_DELAY_MS = APP_CONFIG.typewriter.thinkingDelayMs
const CONTENT_TYPEWRITER_DELAY_MS = APP_CONFIG.typewriter.contentDelayMs

function normalizeToolPayload(payload) {
  if (payload == null) return ''
  if (typeof payload === 'string') {
    const trimmed = payload.trim()
    if (!trimmed) return ''
    try {
      return JSON.stringify(JSON.parse(trimmed), null, 2)
    } catch {
      return payload
    }
  }
  if (typeof payload === 'object') {
    try {
      return JSON.stringify(payload, null, 2)
    } catch {
      return String(payload)
    }
  }
  return String(payload)
}

function getApiBase() {
  const baseUrl = import.meta.env.BASE_URL || '/'
  return baseUrl.replace(/\/$/, '')
}

async function apiLogin(username, password) {
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

async function apiRegister(username, password) {
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

async function apiDeleteSession(token, chatId) {
  const res = await fetch(`${getApiBase()}/api/session/${chatId}`, {
    method: 'DELETE',
    headers: { 'Authorization': `Bearer ${token}` }
  })
  if (!res.ok) throw new Error('Failed to delete session')
  return res.json()
}

async function apiListSessions(token) {
  const res = await fetch(`${getApiBase()}/api/sessions`, {
    headers: { 'Authorization': `Bearer ${token}` }
  })
  if (!res.ok) throw new Error('Failed to list sessions')
  return res.json()
}

async function apiGetHistory(token, limit = 100, chatId) {
  const res = await fetch(`${getApiBase()}/api/history?limit=${limit}&chat_id=${encodeURIComponent(chatId)}`, {
    headers: { 'Authorization': `Bearer ${token}` }
  })
  if (!res.ok) throw new Error('Failed to fetch history')
  return res.json()
}

function parseServerTimestamp(value) {
  if (!value) return new Date().toISOString()
  // Handle both Unix timestamp (seconds) and ISO string
  if (typeof value === 'number') {
    return new Date(value * (value > 1e12 ? 1 : 1000)).toISOString()
  }
  if (typeof value === 'string') {
    // Check if it's a Unix timestamp string
    const num = Number(value)
    if (!isNaN(num)) {
      return new Date(num > 1e12 ? num : num * 1000).toISOString()
    }
    // Otherwise treat as ISO string
    return new Date(value).toISOString()
  }
  return new Date().toISOString()
}

function AuthModal({ mode, onModeSwitch, onSubmit, loading, error }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit(username, password)
  }

  return (
    <div className="auth-modal-overlay">
      <div className="auth-modal">
        <h2>{mode === 'login' ? '登录' : '注册'}</h2>
        <form onSubmit={handleSubmit}>
          <div className="auth-field">
            <label>用户名</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="请输入用户名"
              required
            />
          </div>
          <div className="auth-field">
            <label>密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="请输入密码"
              required
            />
          </div>
          {error && <div className="auth-error">{error}</div>}
          <button type="submit" className="auth-submit" disabled={loading}>
            {loading ? '处理中...' : (mode === 'login' ? '登录' : '注册')}
          </button>
        </form>
        <div className="auth-switch">
          {mode === 'login' ? '还没有账号？' : '已有账号？'}
          <button type="button" onClick={onModeSwitch}>
            {mode === 'login' ? '注册' : '登录'}
          </button>
        </div>
      </div>
    </div>
  )
}

function App() {
  const [chats, setChats] = useState({})
  const [currentChatId, setCurrentChatId] = useState(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [thinkingEnabled, setThinkingEnabled] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const abortControllerRef = useRef(null)
  const activeChatIdRef = useRef(null)
  const typingQueueRef = useRef([])
  const typingTimerRef = useRef(null)
  const hasStreamedContentRef = useRef(false)
  const persistTimerRef = useRef(null)
  const persistSnapshotRef = useRef(null)

  // Auth state
  const [authToken, setAuthToken] = useState(() => localStorage.getItem(AUTH_TOKEN_KEY))
  const [authUser, setAuthUser] = useState(() => localStorage.getItem(AUTH_USER_KEY))
  const [authLoading, setAuthLoading] = useState(false)
  const [authError, setAuthError] = useState('')
  const [showAuthModal, setShowAuthModal] = useState(false)
  const [authMode, setAuthMode] = useState('login') // 'login' | 'register'

  // Thinking typewriter
  const thinkingQueueRef = useRef([])       // queue of strings to type
  const typingThinkingTimerRef = useRef(null)

  const stopThinkingTypewriter = useCallback(() => {
    if (typingThinkingTimerRef.current) {
      clearTimeout(typingThinkingTimerRef.current)
      typingThinkingTimerRef.current = null
    }
    thinkingQueueRef.current = []
  }, [])

  const drainThinkingQueue = useCallback(() => {
    if (typingThinkingTimerRef.current) {
      clearTimeout(typingThinkingTimerRef.current)
      typingThinkingTimerRef.current = null
    }
    if (thinkingQueueRef.current.length === 0) return ''
    const pending = thinkingQueueRef.current.join('')
    thinkingQueueRef.current = []
    return pending
  }, [])

  const runThinkingTypewriter = useCallback(() => {
    if (typingThinkingTimerRef.current || thinkingQueueRef.current.length === 0) return

    const tick = () => {
      // Get next string from queue
      const next = thinkingQueueRef.current.shift()
      if (next == null) {
        typingThinkingTimerRef.current = null
        return
      }

      // Append this chunk to message.thinking (which is already accumulated)
      setChats(prev => {
        const chatId = activeChatIdRef.current
        const current = prev[chatId]
        if (!current || current.messages.length === 0) return prev
        const messages = [...current.messages]
        const lastMsg = messages[messages.length - 1]
        if (!lastMsg || lastMsg.role !== 'assistant') return prev
        messages[messages.length - 1] = { ...lastMsg, thinking: (lastMsg.thinking || '') + next }
        return { ...prev, [chatId]: { ...current, messages } }
      })

      if (thinkingQueueRef.current.length > 0) {
        typingThinkingTimerRef.current = setTimeout(tick, THINKING_TYPEWRITER_DELAY_MS)
      } else {
        typingThinkingTimerRef.current = null
      }
    }
    typingThinkingTimerRef.current = setTimeout(tick, THINKING_TYPEWRITER_DELAY_MS)
  }, [])

  const enqueueThinking = useCallback((text) => {
    if (!text) return
    // Split each chunk into individual characters for typewriter effect
    thinkingQueueRef.current.push(...Array.from(text))
    runThinkingTypewriter()
  }, [runThinkingTypewriter])

  // Load chats from localStorage
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    let initialChats = {}
    let initialChatId = null

    if (stored) {
      try {
        const parsed = JSON.parse(stored)
        const lastActive = localStorage.getItem('lastActiveChat')
        if (lastActive && parsed[lastActive]) {
          initialChats = parsed
          initialChatId = lastActive
        } else {
          const firstKey = Object.keys(parsed)[0]
          if (firstKey) {
            initialChats = parsed
            initialChatId = firstKey
          }
        }
      } catch { /* ignore */ }
    }

    // Set initial chats (may be empty or from localStorage)
    setChats(initialChats)
    if (initialChatId) {
      setCurrentChatId(initialChatId)
    } else if (Object.keys(initialChats).length === 0) {
      const chatId = Date.now().toString()
      setChats({ [chatId]: { id: chatId, title: '新对话', createdAt: new Date().toISOString(), messages: [] } })
      setCurrentChatId(chatId)
    }
  }, [])

  // Load session list from server when authenticated (lazy loading - history loaded on demand)
  const historyMergedRef = useRef(false)
  useEffect(() => {
    if (!authToken || historyMergedRef.current) return
    historyMergedRef.current = true

    const stored = localStorage.getItem(STORAGE_KEY)
    let localChats = {}
    if (stored) {
      try {
        localChats = JSON.parse(stored)
      } catch { /* ignore */ }
    }

    apiListSessions(authToken).then(data => {
      if (data.sessions && data.sessions.length > 0) {
        setChats(prev => {
          const updated = { ...prev }
          data.sessions.forEach(session => {
            const chatId = session.chat_id
            if (updated[chatId]) {
              // Update title if we have a local chat
              updated[chatId] = { ...updated[chatId], title: session.title }
            } else {
              // Create placeholder chat from server session
              updated[chatId] = {
                id: chatId,
                title: session.title,
                createdAt: new Date().toISOString(),
                messages: []
              }
            }
          })
          return updated
        })
      }
    }).catch(e => {
      console.error('Failed to load session list:', e)
    })
  }, [authToken])

  const persistChatsNow = useCallback((newChats) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(newChats))
  }, [])

  const schedulePersistChats = useCallback((newChats) => {
    persistSnapshotRef.current = newChats
    if (persistTimerRef.current) return

    persistTimerRef.current = setTimeout(() => {
      persistTimerRef.current = null
      if (persistSnapshotRef.current) {
        persistChatsNow(persistSnapshotRef.current)
        persistSnapshotRef.current = null
      }
    }, PERSIST_DEBOUNCE_MS)
  }, [persistChatsNow])

  const flushPersistChats = useCallback(() => {
    if (persistTimerRef.current) {
      clearTimeout(persistTimerRef.current)
      persistTimerRef.current = null
    }
    if (persistSnapshotRef.current) {
      persistChatsNow(persistSnapshotRef.current)
      persistSnapshotRef.current = null
    }
  }, [persistChatsNow])

  useEffect(() => {
    activeChatIdRef.current = currentChatId
  }, [currentChatId])

  const stopTypewriter = useCallback(() => {
    if (typingTimerRef.current) {
      clearTimeout(typingTimerRef.current)
      typingTimerRef.current = null
    }
    typingQueueRef.current = []
  }, [])


  const runTypewriter = useCallback(() => {
    if (typingTimerRef.current || typingQueueRef.current.length === 0) return

    const tick = () => {
      const nextChar = typingQueueRef.current.shift()
      if (nextChar == null) {
        typingTimerRef.current = null
        return
      }

      const shouldPersistAfterTick = typingQueueRef.current.length === 0

      setChats(prev => {
        const chatId = activeChatIdRef.current
        const current = prev[chatId]
        if (!current || current.messages.length === 0) return prev

        const messages = [...current.messages]
        const lastIndex = messages.length - 1
        const lastMsg = messages[lastIndex]
        if (!lastMsg || lastMsg.role !== 'assistant') return prev

        const nextLastMsg = {
          ...lastMsg,
          content: (lastMsg.content || '') + nextChar
        }

        messages[lastIndex] = nextLastMsg
        const updated = {
          ...prev,
          [chatId]: {
            ...current,
            messages
          }
        }
        if (shouldPersistAfterTick) {
          schedulePersistChats(updated)
        }
        return updated
      })

      if (typingQueueRef.current.length > 0) {
        // 打字的速度，小则更快
        typingTimerRef.current = setTimeout(tick, CONTENT_TYPEWRITER_DELAY_MS)
      } else {
        typingTimerRef.current = null
      }
    }
    // 打字的速度，小则更快
    typingTimerRef.current = setTimeout(tick, CONTENT_TYPEWRITER_DELAY_MS)
  }, [schedulePersistChats])

  const enqueueTypewriter = useCallback((text) => {
    if (!text) return
    typingQueueRef.current.push(...Array.from(text))
    runTypewriter()
  }, [runTypewriter])

  useEffect(() => {
    return () => {
      if (typingTimerRef.current) {
        clearTimeout(typingTimerRef.current)
      }
      if (typingThinkingTimerRef.current) {
        clearTimeout(typingThinkingTimerRef.current)
      }
      flushPersistChats()
    }
  }, [flushPersistChats])

  const createNewChat = useCallback(() => {
    const chatId = Date.now().toString()
    const newChat = {
      id: chatId,
      title: '新对话',
      createdAt: new Date().toISOString(),
      messages: []
    }
    setChats(prev => {
      const updated = { ...prev, [chatId]: newChat }
      schedulePersistChats(updated)
      return updated
    })
    setCurrentChatId(chatId)
    setSidebarOpen(false)
  }, [schedulePersistChats])

  // Auth handlers
  const handleAuthLogin = useCallback(async (username, password) => {
    setAuthError('')
    setAuthLoading(true)
    try {
      const data = await apiLogin(username, password)
      setAuthToken(data.token)
      setAuthUser(username)
      localStorage.setItem(AUTH_TOKEN_KEY, data.token)
      localStorage.setItem(AUTH_USER_KEY, username)
      setShowAuthModal(false)
      // Load history after login
      loadHistoryFromServer(data.token)
    } catch (e) {
      setAuthError(e.message)
    } finally {
      setAuthLoading(false)
    }
  }, [])

  const handleAuthRegister = useCallback(async (username, password) => {
    setAuthError('')
    setAuthLoading(true)
    try {
      await apiRegister(username, password)
      // Auto login after register
      const data = await apiLogin(username, password)
      setAuthToken(data.token)
      setAuthUser(username)
      localStorage.setItem(AUTH_TOKEN_KEY, data.token)
      localStorage.setItem(AUTH_USER_KEY, username)
      setShowAuthModal(false)
    } catch (e) {
      setAuthError(e.message)
    } finally {
      setAuthLoading(false)
    }
  }, [])

  const handleLogout = useCallback(() => {
    setAuthToken(null)
    setAuthUser(null)
    localStorage.removeItem(AUTH_TOKEN_KEY)
    localStorage.removeItem(AUTH_USER_KEY)
    // Clear all chats and start fresh
    const chatId = Date.now().toString()
    setChats({ [chatId]: { id: chatId, title: '新对话', createdAt: new Date().toISOString(), messages: [] } })
    setCurrentChatId(chatId)
    // Clear server_history from localStorage
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      try {
        const chats = JSON.parse(stored)
        delete chats['server_history']
        localStorage.setItem(STORAGE_KEY, JSON.stringify(chats))
      } catch { /* ignore */ }
    }
  }, [])

  const switchChat = useCallback((chatId) => {
    setCurrentChatId(chatId)
    localStorage.setItem('lastActiveChat', chatId)
    setSidebarOpen(false)

    // Lazy load history for the switched chat
    if (authToken && chatId && chatId !== 'server_history') {
      setChats(prev => {
        const chat = prev[chatId]
        // Only fetch if messages are empty (not yet loaded)
        if (chat && chat.messages.length === 0) {
          apiGetHistory(authToken, 100, chatId).then(data => {
            if (data.history && data.history.length > 0) {
              setChats(currentChats => {
                const currentChat = currentChats[chatId]
                if (!currentChat || currentChat.messages.length > 0) return currentChats

                const newMessages = data.history.map((h, idx) => ({
                  role: h.role,
                  content: h.content || '',
                  thinking: h.thinking || '',
                  thinkingCompleted: h.thinking_completed ?? !!h.thinking,
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
                  serverId: h.id || null // Use server ID for stable keys
                }))

                return {
                  ...currentChats,
                  [chatId]: { ...currentChat, messages: newMessages }
                }
              })
            }
          }).catch(e => {
            console.error(`Failed to load history for ${chatId}:`, e)
          })
        }
        return prev
      })
    }
  }, [authToken])

  const deleteChat = useCallback(async (chatId, e) => {
    e.stopPropagation()
    // Call backend API to delete session
    if (authToken && chatId !== 'server_history') {
      try {
        await apiDeleteSession(authToken, chatId)
      } catch (err) {
        console.error('Failed to delete session on server:', err)
      }
    }
    setChats(prev => {
      const updated = { ...prev }
      delete updated[chatId]
      schedulePersistChats(updated)
      return updated
    })
    if (currentChatId === chatId) {
      const keys = Object.keys(chats).filter(k => k !== chatId)
      if (keys.length > 0) {
        setCurrentChatId(keys[0])
      } else {
        createNewChat()
      }
    }
  }, [currentChatId, chats, schedulePersistChats, createNewChat, authToken])

  const updateChatTitle = useCallback((chatId, firstMessage) => {
    const title = firstMessage.substring(0, 30) + (firstMessage.length > 30 ? '...' : '')
    setChats(prev => {
      const updated = {
        ...prev,
        [chatId]: { ...prev[chatId], title }
      }
      schedulePersistChats(updated)
      return updated
    })
  }, [schedulePersistChats])

  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || isGenerating) return
    if (!authToken) {
      setShowAuthModal(true)
      return
    }

    stopTypewriter()
    stopThinkingTypewriter()
    hasStreamedContentRef.current = false

    const userMsg = {
      role: 'user',
      content: text,
      timestamp: new Date().toISOString()
    }

    setChats(prev => {
      const updated = {
        ...prev,
        [currentChatId]: {
          ...prev[currentChatId],
          messages: [...prev[currentChatId].messages, userMsg]
        }
      }
      schedulePersistChats(updated)
      return updated
    })

    if (chats[currentChatId].messages.length === 0) {
      updateChatTitle(currentChatId, text)
    }

    setIsGenerating(true)
    setSidebarOpen(false)
    abortControllerRef.current = new AbortController()

    const assistantMsg = {
      role: 'assistant',
      content: '',
      thinking: '',
      timestamp: new Date().toISOString(),
      tool_calls: [],
      tool_traces: [],
      thinkingCompleted: false
    }

    // Add placeholder
    setChats(prev => {
      const updated = {
        ...prev,
        [currentChatId]: {
          ...prev[currentChatId],
          messages: [...prev[currentChatId].messages, assistantMsg]
        }
      }
      schedulePersistChats(updated)
      return updated
    })

    try {
      const baseUrl = import.meta.env.BASE_URL || '/'
      const apiUrl = `${baseUrl}api/chat`
      const body = {
        message: text,
        thinking: thinkingEnabled,
        stream: true
      }
      // Only send chat_id if authenticated (not server_history)
      if (authToken && currentChatId !== 'server_history') {
        body.chat_id = currentChatId
      }
      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify(body),
        signal: abortControllerRef.current.signal
      })

      if (!response.ok) {
        if (response.status === 401) {
          handleLogout()
          throw new Error('登录已过期，请重新登录')
        }
        throw new Error('HTTP ' + response.status)
      }

      if (response.body) {
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''  // 用于处理不完整的 SSE 行
        let currentEvent = null

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })

          // 处理 buffer 中的完整行
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''  // 保留最后一行（可能不完整）

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              currentEvent = line.substring(7).trim()
            } else if (line.startsWith('data: ')) {
              const data = line.substring(6).trim()
              if (!data) continue

              try {
                const json = JSON.parse(data)

                if (currentEvent === 'content') {
                  hasStreamedContentRef.current = true
                  enqueueTypewriter(json.content)
                  continue
                }

                if (currentEvent === 'thinking') {
                  enqueueThinking(json.content)
                  continue
                }

                if (currentEvent === 'error') {
                  stopTypewriter()
                }

                const capturedEvent = currentEvent
                setChats(prev => {
                  const updatedChats = { ...prev }
                  const chat = { ...updatedChats[currentChatId] }
                  const messages = [...chat.messages]
                  const lastMsg = { ...messages[messages.length - 1] }
                  let updated = false
                  let persistNeeded = false

                  switch (capturedEvent) {
                    case 'tool_call':
                      if (!lastMsg.tool_calls) lastMsg.tool_calls = []
                      if (!lastMsg.tool_traces) lastMsg.tool_traces = []
                      const toolArguments = json.arguments ?? json.args ?? null
                      if (json.tool_name && !lastMsg.tool_calls.includes(json.tool_name)) {
                        lastMsg.tool_calls = [...lastMsg.tool_calls, json.tool_name]
                      }
                      {
                        const callId = String(
                          json.tool_call_id || `call_${Date.now()}_${lastMsg.tool_traces.length}`
                        )
                        const existingIndex = lastMsg.tool_traces.findIndex(item =>
                          String(item.tool_call_id || '') === callId
                        )

                        if (existingIndex >= 0) {
                          const nextTraces = [...lastMsg.tool_traces]
                          const existing = nextTraces[existingIndex]
                          nextTraces[existingIndex] = {
                            ...existing,
                            tool_call_id: callId,
                            tool_name: json.tool_name || existing.tool_name || 'unknown_tool',
                            arguments: toolArguments ?? existing.arguments ?? null,
                            status: existing.status === 'completed' ? 'completed' : 'running'
                          }
                          lastMsg.tool_traces = nextTraces
                        } else {
                          lastMsg.tool_traces = [
                            ...lastMsg.tool_traces,
                            {
                              tool_call_id: callId,
                              tool_name: json.tool_name || 'unknown_tool',
                              arguments: toolArguments,
                              result: null,
                              status: 'running'
                            }
                          ]
                        }
                      }
                      updated = true
                      persistNeeded = true
                      break
                    case 'tool_result':
                      if (!lastMsg.tool_traces) lastMsg.tool_traces = []
                      {
                        const resultCallId = json.tool_call_id ? String(json.tool_call_id) : null
                        let targetIndex = lastMsg.tool_traces.findIndex(item =>
                          resultCallId && String(item.tool_call_id || '') === resultCallId
                        )
                        if (targetIndex < 0 && json.tool_name) {
                          targetIndex = lastMsg.tool_traces.findIndex(item =>
                            item.tool_name === json.tool_name && item.status !== 'completed'
                          )
                        }
                        if (targetIndex >= 0) {
                          const nextTraces = [...lastMsg.tool_traces]
                          nextTraces[targetIndex] = {
                            ...nextTraces[targetIndex],
                            result: json.result,
                            tool_name: json.tool_name || nextTraces[targetIndex].tool_name,
                            status: 'completed'
                          }
                          lastMsg.tool_traces = nextTraces
                        } else {
                          lastMsg.tool_traces = [
                            ...lastMsg.tool_traces,
                            {
                              tool_call_id: resultCallId || `result_${Date.now()}_${lastMsg.tool_traces.length}`,
                              tool_name: json.tool_name || 'unknown_tool',
                              arguments: null,
                              result: json.result,
                              status: 'completed'
                            }
                          ]
                        }
                      }
                      updated = true
                      persistNeeded = true
                      break
                    case 'done':
                      {
                        const pendingThinking = drainThinkingQueue()
                        if (pendingThinking) {
                          lastMsg.thinking = (lastMsg.thinking || '') + pendingThinking
                        }
                      }
                      lastMsg.thinkingCompleted = true
                      if (json.usage) {
                        lastMsg.usage = json.usage
                      }
                      if (json.content && !hasStreamedContentRef.current) {
                        hasStreamedContentRef.current = true
                        enqueueTypewriter(json.content)
                      }
                      updated = true
                      persistNeeded = true
                      break
                    case 'error':
                      lastMsg.content = `Error: ${json.message}`
                      updated = true
                      persistNeeded = true
                      break
                  }

                  if (updated) {
                    messages[messages.length - 1] = lastMsg
                    chat.messages = messages
                    updatedChats[currentChatId] = chat
                    if (persistNeeded) {
                      schedulePersistChats(updatedChats)
                    }
                    return updatedChats
                  }
                  return prev
                })
              } catch (e) {
                console.error('SSE parse error:', e)
              }
            }
          }
        }
      } else {
        const data = await response.json()
        setChats(prev => {
          const updatedChats = { ...prev }
          const chat = { ...updatedChats[currentChatId] }
          const messages = [...chat.messages]
          const lastMsg = { ...messages[messages.length - 1] }
          lastMsg.content = ''
          lastMsg.tool_calls = data.tool_calls || []
          lastMsg.thinkingCompleted = true
          messages[messages.length - 1] = lastMsg
          chat.messages = messages
          updatedChats[currentChatId] = chat
          schedulePersistChats(updatedChats)
          return updatedChats
        })
        enqueueTypewriter(data.response || '')
      }
    } catch (error) {
      if (error.name !== 'AbortError') {
        stopTypewriter()
        console.error('Error:', error)
        setChats(prev => {
          const updatedChats = { ...prev }
          const chat = { ...updatedChats[currentChatId] }
          const messages = [...chat.messages]
          const lastMsg = { ...messages[messages.length - 1] }
          lastMsg.content = '错误: ' + error.message
          messages[messages.length - 1] = lastMsg
          chat.messages = messages
          updatedChats[currentChatId] = chat
          schedulePersistChats(updatedChats)
          return updatedChats
        })
      }
    } finally {
      flushPersistChats()
      setIsGenerating(false)
      abortControllerRef.current = null
    }
  }, [
    currentChatId,
    isGenerating,
    thinkingEnabled,
    chats,
    schedulePersistChats,
    updateChatTitle,
    stopTypewriter,
    stopThinkingTypewriter,
    drainThinkingQueue,
    enqueueTypewriter,
    flushPersistChats,
    authToken
  ])

  const stopGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    stopTypewriter()
    stopThinkingTypewriter()
  }, [stopTypewriter, stopThinkingTypewriter])

  const currentChat = chats[currentChatId]

  return (
    <div className="app-container">
      <div
        className={`sidebar-overlay ${sidebarOpen ? 'active' : ''}`}
        onClick={() => setSidebarOpen(false)}
      />
      {showAuthModal && (
        <AuthModal
          mode={authMode}
          onModeSwitch={() => setAuthMode(authMode === 'login' ? 'register' : 'login')}
          onSubmit={authMode === 'login' ? handleAuthLogin : handleAuthRegister}
          loading={authLoading}
          error={authError}
        />
      )}
      <Sidebar
        chats={chats}
        currentChatId={currentChatId}
        onSwitchChat={switchChat}
        onDeleteChat={deleteChat}
        onNewChat={createNewChat}
        isOpen={sidebarOpen}
        authUser={authUser}
        onLogout={handleLogout}
        onLoginClick={() => { setShowAuthModal(true); setAuthMode('login') }}
        onRegisterClick={() => { setShowAuthModal(true); setAuthMode('register') }}
      />
      <MainContent
        chat={currentChat}
        isGenerating={isGenerating}
        thinkingEnabled={thinkingEnabled}
        onSendMessage={sendMessage}
        onStopGeneration={stopGeneration}
        onToggleThinking={() => setThinkingEnabled(!thinkingEnabled)}
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        isAuthenticated={!!authToken}
        onLoginClick={() => { setShowAuthModal(true); setAuthMode('login') }}
      />
    </div>
  )
}

function Sidebar({ chats, currentChatId, onSwitchChat, onDeleteChat, onNewChat, isOpen, authUser, onLogout, onLoginClick, onRegisterClick }) {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const sortedChats = Object.values(chats).sort((a, b) =>
    new Date(b.createdAt) - new Date(a.createdAt)
  )

  const handleLogout = () => {
    setSettingsOpen(false)
    onLogout()
  }

  return (
    <div className={`sidebar ${isOpen ? 'open' : ''}`}>
      <div className="sidebar-header">
        <div className="logo-area">
          <div className="logo-icon">⚡</div>
          <span className="logo-text">AgentForge</span>
        </div>
        <button className="new-chat-btn" onClick={onNewChat}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          新建对话
        </button>
      </div>
      <div className="chat-list">
        {sortedChats.map(chat => (
          <div
            key={chat.id}
            className={`chat-item ${chat.id === currentChatId ? 'active' : ''}`}
            onClick={() => onSwitchChat(chat.id)}
          >
            <div className="chat-item-icon">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <span className="chat-item-title">{chat.title}</span>
            <button className="chat-item-delete" onClick={(e) => onDeleteChat(chat.id, e)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        ))}
      </div>
      <div className="sidebar-auth">
        {authUser ? (
          <div className="auth-user-info">
            <span className="auth-username">{authUser}</span>
            <button className="auth-logout-btn" onClick={onLogout}>退出</button>
          </div>
        ) : (
          <div className="auth-buttons">
            <button className="auth-login-btn" onClick={onLoginClick}>登录</button>
            <button className="auth-register-btn" onClick={onRegisterClick}>注册</button>
          </div>
        )}
      </div>
      {authUser && (
        <div className="sidebar-user-badge">
          {settingsOpen && (
            <div className="settings-dropdown">
              <button className="settings-dropdown-item danger" onClick={handleLogout}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                  <polyline points="16 17 21 12 16 7" />
                  <line x1="21" y1="12" x2="9" y2="12" />
                </svg>
                退出登录
              </button>
            </div>
          )}
          <div className="user-badge-avatar">
            {authUser.charAt(0).toUpperCase()}
          </div>
          <div className="user-badge-info">
            <span className="user-badge-name">{authUser}</span>
            <span className="user-badge-status">已登录</span>
          </div>
          <button className="user-badge-settings" onClick={() => setSettingsOpen(!settingsOpen)}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3" />
              <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
            </svg>
          </button>
        </div>
      )}
    </div>
  )
}

function MainContent({
  chat,
  isGenerating,
  thinkingEnabled,
  onSendMessage,
  onStopGeneration,
  onToggleThinking,
  onToggleSidebar,
  isAuthenticated,
  onLoginClick
}) {
  const [inputValue, setInputValue] = useState('')
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE_MESSAGES)
  const messagesEndRef = useRef(null)
  const messages = chat?.messages || []
  const hiddenCount = Math.max(0, messages.length - visibleCount)
  const visibleMessages = hiddenCount > 0 ? messages.slice(-visibleCount) : messages

  useEffect(() => {
    setVisibleCount(INITIAL_VISIBLE_MESSAGES)
  }, [chat?.id])

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: messages.length > 120 ? 'auto' : 'smooth' })
    }
  }, [messages])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (inputValue.trim()) {
      onSendMessage(inputValue)
      setInputValue('')
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const autoResize = (e) => {
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 150) + 'px'
  }

  const currentChatTitle = chat?.title || '新对话'

  return (
    <div className="main-content">
      <header className="header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button className="menu-btn" onClick={onToggleSidebar}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
          <span className="header-title">{currentChatTitle}</span>
        </div>
        </header>

      <div className="messages-container">
        {messages.length === 0 ? (
          <WelcomeScreen onSendMessage={onSendMessage} />
        ) : (
          <>
            {hiddenCount > 0 && (
              <div className="load-more-wrap">
                <button
                  type="button"
                  className="load-more-btn"
                  onClick={() => setVisibleCount(prev => prev + MESSAGE_PAGE_SIZE)}
                >
                  加载更早消息 ({hiddenCount} 条)
                </button>
              </div>
            )}
            {visibleMessages.map((msg, idx) => (
              <Message
                key={msg.serverId || msg.timestamp || `${msg.role}-${idx}`}
                message={msg}
                thinkingEnabled={thinkingEnabled}
              />
            ))}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="input-container">
        <form className="input-wrapper" onSubmit={handleSubmit}>
          <div className="input-box">
            <textarea
              className="input-textarea"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              onInput={autoResize}
              placeholder={isAuthenticated ? "输入消息..." : "请先登录后发送消息"}
              rows={1}
              disabled={isGenerating}
            />
            {isGenerating ? (
              <button
                type="button"
                className="stop-btn"
                onClick={onStopGeneration}
              >
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <rect x="6" y="6" width="12" height="12" rx="2" />
                </svg>
              </button>
            ) : (
              <button
                type="submit"
                className="send-btn"
                disabled={isGenerating || !inputValue.trim()}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="12" y1="19" x2="12" y2="5" />
                  <polyline points="5 12 12 5 19 12" />
                </svg>
              </button>
            )}
          </div>
          <div className="input-toolbar">
            <div className="toolbar-left">
              <button
                type="button"
                className={`toolbar-btn ${thinkingEnabled ? 'active' : ''}`}
                onClick={onToggleThinking}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 6v6l4 2" />
                </svg>
                深度思考
              </button>
              <button type="button" className="toolbar-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
                智能搜索
              </button>
            </div>
            <div className="input-hints">
              <span>Enter 发送 · Shift+Enter 换行</span>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}

const Message = memo(function Message({ message, thinkingEnabled }) {
  const [thinkingExpanded, setThinkingExpanded] = useState(true)
  const [expandedToolCalls, setExpandedToolCalls] = useState({})
  const isUser = message.role === 'user'
  const toolTraces = message.tool_traces || []

  const toggleToolCall = useCallback((toolCallId) => {
    setExpandedToolCalls(prev => ({
      ...prev,
      [toolCallId]: !prev[toolCallId]
    }))
  }, [])

  return (
    <div className={`message ${isUser ? 'user' : 'assistant'}`}>
      <div className="message-content">
        {!isUser && message.thinking && thinkingEnabled && (
          <ThinkingIndicator
            thinking={message.thinking}
            completed={message.thinkingCompleted}
            expanded={thinkingExpanded}
            onToggle={() => setThinkingExpanded(!thinkingExpanded)}
          />
        )}

        {!isUser && toolTraces.length > 0 && (
          <div className="tool-call-list">
            {toolTraces.map((trace, idx) => {
              const toolCallId = trace.tool_call_id || `tool_call_${idx}`
              const expanded = !!expandedToolCalls[toolCallId]
              const isCompleted = trace.status === 'completed'
              const argsText = normalizeToolPayload(trace.arguments)
              const resultText = normalizeToolPayload(trace.result)

              return (
                <div key={toolCallId} className={`tool-call-card ${isCompleted ? 'completed' : 'running'}`}>
                  <button
                    type="button"
                    className="tool-call-header"
                    onClick={() => toggleToolCall(toolCallId)}
                  >
                    <div className="tool-call-left">
                      {isCompleted ? (
                        <span className="tool-status-icon done">✓</span>
                      ) : (
                        <span className="tool-status-icon spinner" aria-hidden="true" />
                      )}
                      <span className="tool-name">{trace.tool_name || 'tool'}</span>
                      <span className={`tool-status-text ${isCompleted ? 'done' : 'running'}`}>
                        {isCompleted ? '已完成' : '调用中...'}
                      </span>
                    </div>
                    <span className="tool-call-toggle">{expanded ? '收起' : '查看详情'}</span>
                  </button>

                  {expanded && (
                    <div className="tool-call-details">
                      <div className="tool-detail-item">
                        <div className="tool-detail-label">参数</div>
                        <pre>{argsText || '无参数'}</pre>
                      </div>

                      <div className="tool-detail-item">
                        <div className="tool-detail-label">结果</div>
                        <pre>{resultText || (isCompleted ? '无返回' : '等待工具执行完成...')}</pre>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}

        <div className={`message-body ${isUser ? 'user-bubble' : 'assistant-text'}`}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        </div>

        {!isUser && message.usage && (
          <div className="usage-info">
            <span>输入: {message.usage.input_tokens ?? 0} tokens</span>
            <span>输出: {message.usage.output_tokens ?? 0} tokens</span>
            {message.usage.cache_write_tokens != null && (
              <span>缓存写入: {message.usage.cache_write_tokens}</span>
            )}
            {message.usage.cache_read_tokens != null && (
              <span>缓存读取: {message.usage.cache_read_tokens}</span>
            )}
          </div>
        )}
      </div>
    </div>
  )
})

function ThinkingIndicator({ thinking, completed, expanded, onToggle }) {
  return (
    <div className="thinking-indicator" onClick={onToggle}>
      <div className={`thinking-header ${completed ? 'thinking-completed' : ''}`}>
        {completed ? (
          '✓'
        ) : (
          <div className="thinking-dots">
            <span /><span /><span />
          </div>
        )}
        <span className="thinking-status">{completed ? '已思考' : '思考中...'}</span>
        <span className="thinking-toggle">[{expanded ? '收起' : '展开'}]</span>
      </div>
      <div className={`thinking-content ${expanded ? 'expanded' : ''} ${completed ? 'completed' : ''}`}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{thinking}</ReactMarkdown>
      </div>
    </div>
  )
}

function WelcomeScreen({ onSendMessage }) {
  const examples = [
    { title: '工具调用', desc: '分开两次调用工具，计算 431*131 结果再乘2', text: '分开两次调用工具，计算 431*131 结果再乘2' },
    { title: '量子计算', desc: '用简单易懂的方式解释', text: '解释量子计算的基本原理' },
    { title: '科技趋势', desc: 'AI、新能源、半导体方向', text: '分析当前科技行业的发展趋势' },
    { title: '书籍推荐', desc: '不同水平阶段的经典书籍', text: '推荐几本提升编程技能的书籍' },
  ]

  return (
    <div className="welcome-screen">
      <div className="welcome-logo">⚡</div>
      <h1 className="welcome-title">AgentForge</h1>
      <p className="welcome-subtitle">基于大模型的智能助手</p>
      <div className="welcome-examples">
        {examples.map((ex, idx) => (
          <div
            key={idx}
            className="example-card"
            onClick={() => onSendMessage(ex.text)}
          >
            <div className="example-card-title">{ex.title}</div>
            <div className="example-card-desc">{ex.desc}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default App