import { useState, useEffect, useRef, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const STORAGE_KEY = 'agentforge_chats_v3'

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

  // Load chats from localStorage
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      try {
        const parsed = JSON.parse(stored)
        const lastActive = localStorage.getItem('lastActiveChat')
        if (lastActive && parsed[lastActive]) {
          setChats(parsed)
          setCurrentChatId(lastActive)
        } else {
          const firstKey = Object.keys(parsed)[0]
          if (firstKey) {
            setChats(parsed)
            setCurrentChatId(firstKey)
          } else {
            const chatId = Date.now().toString()
            const newChat = {
              id: chatId,
              title: '新对话',
              createdAt: new Date().toISOString(),
              messages: []
            }
            setChats({ [chatId]: newChat })
            setCurrentChatId(chatId)
          }
        }
      } catch {
        const chatId = Date.now().toString()
        const newChat = {
          id: chatId,
          title: '新对话',
          createdAt: new Date().toISOString(),
          messages: []
        }
        setChats({ [chatId]: newChat })
        setCurrentChatId(chatId)
      }
    } else {
      const chatId = Date.now().toString()
      const newChat = {
        id: chatId,
        title: '新对话',
        createdAt: new Date().toISOString(),
        messages: []
      }
      setChats({ [chatId]: newChat })
      setCurrentChatId(chatId)
    }
  }, [])

  const saveChats = useCallback((newChats) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(newChats))
  }, [])

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
        saveChats(updated)
        return updated
      })

      if (typingQueueRef.current.length > 0) {
        // 打字的速度，小则更快
        typingTimerRef.current = setTimeout(tick, 18)
      } else {
        typingTimerRef.current = null
      }
    }
    // 打字的速度，小则更快
    typingTimerRef.current = setTimeout(tick, 18)
  }, [saveChats])

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
    }
  }, [])

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
      saveChats(updated)
      return updated
    })
    setCurrentChatId(chatId)
    setSidebarOpen(false)
  }, [saveChats])

  const switchChat = useCallback((chatId) => {
    setCurrentChatId(chatId)
    localStorage.setItem('lastActiveChat', chatId)
    setSidebarOpen(false)
  }, [])

  const deleteChat = useCallback((chatId, e) => {
    e.stopPropagation()
    setChats(prev => {
      const updated = { ...prev }
      delete updated[chatId]
      saveChats(updated)
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
  }, [currentChatId, chats, saveChats, createNewChat])

  const updateChatTitle = useCallback((chatId, firstMessage) => {
    const title = firstMessage.substring(0, 30) + (firstMessage.length > 30 ? '...' : '')
    setChats(prev => {
      const updated = {
        ...prev,
        [chatId]: { ...prev[chatId], title }
      }
      saveChats(updated)
      return updated
    })
  }, [saveChats])

  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || isGenerating) return

    stopTypewriter()
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
      saveChats(updated)
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
      saveChats(updated)
      return updated
    })

    try {
      const basePath = window.location.pathname.replace(/\/[^/]*$/, '') || ''
      const apiUrl = `${basePath}/api/chat`
      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          thinking: thinkingEnabled,
          stream: true
        }),
        signal: abortControllerRef.current.signal
      })

      if (!response.ok) throw new Error('HTTP ' + response.status)

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

                if (currentEvent === 'error') {
                  stopTypewriter()
                }

                setChats(prev => {
                  const updatedChats = { ...prev }
                  const chat = { ...updatedChats[currentChatId] }
                  const messages = [...chat.messages]
                  const lastMsg = { ...messages[messages.length - 1] }
                  let updated = false

                  switch (currentEvent) {
                    case 'thinking':
                      lastMsg.thinking = json.content
                      updated = true
                      break
                    case 'tool_call':
                      if (json.tool_name && !lastMsg.tool_calls.includes(json.tool_name)) {
                        lastMsg.tool_calls = [...lastMsg.tool_calls, json.tool_name]
                      }
                      updated = true
                      break
                    case 'tool_result':
                      // Store tool results for potential display
                      if (!lastMsg.tool_results) lastMsg.tool_results = []
                      lastMsg.tool_results.push({
                        tool_name: json.tool_name,
                        result: json.result,
                        tool_call_id: json.tool_call_id
                      })
                      updated = true
                      break
                    case 'done':
                      lastMsg.thinkingCompleted = true
                      if (json.content && !hasStreamedContentRef.current) {
                        hasStreamedContentRef.current = true
                        enqueueTypewriter(json.content)
                      }
                      updated = true
                      break
                    case 'error':
                      lastMsg.content = `Error: ${json.message}`
                      updated = true
                      break
                  }

                  if (updated) {
                    messages[messages.length - 1] = lastMsg
                    chat.messages = messages
                    updatedChats[currentChatId] = chat
                    saveChats(updatedChats)
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
          saveChats(updatedChats)
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
          saveChats(updatedChats)
          return updatedChats
        })
      }
    } finally {
      setIsGenerating(false)
      abortControllerRef.current = null
    }
  }, [
    currentChatId,
    isGenerating,
    thinkingEnabled,
    chats,
    saveChats,
    updateChatTitle,
    stopTypewriter,
    enqueueTypewriter
  ])

  const stopGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    stopTypewriter()
  }, [stopTypewriter])

  const currentChat = chats[currentChatId]

  return (
    <div className="app-container">
      <div
        className={`sidebar-overlay ${sidebarOpen ? 'active' : ''}`}
        onClick={() => setSidebarOpen(false)}
      />
      <Sidebar
        chats={chats}
        currentChatId={currentChatId}
        onSwitchChat={switchChat}
        onDeleteChat={deleteChat}
        onNewChat={createNewChat}
        isOpen={sidebarOpen}
      />
      <MainContent
        chat={currentChat}
        isGenerating={isGenerating}
        thinkingEnabled={thinkingEnabled}
        onSendMessage={sendMessage}
        onStopGeneration={stopGeneration}
        onToggleThinking={() => setThinkingEnabled(!thinkingEnabled)}
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
      />
    </div>
  )
}

function Sidebar({ chats, currentChatId, onSwitchChat, onDeleteChat, onNewChat, isOpen }) {
  const sortedChats = Object.values(chats).sort((a, b) =>
    new Date(b.createdAt) - new Date(a.createdAt)
  )

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
  onToggleSidebar
}) {
  const [inputValue, setInputValue] = useState('')
  const messagesEndRef = useRef(null)
  const messages = chat?.messages || []

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
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
        <div className="header-actions">
          {isGenerating && (
            <button className="header-btn" onClick={onStopGeneration}>
              <svg viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
              停止
            </button>
          )}
        </div>
      </header>

      <div className="messages-container">
        {messages.length === 0 ? (
          <WelcomeScreen onSendMessage={onSendMessage} />
        ) : (
          messages.map((msg, idx) => (
            <Message
              key={idx}
              message={msg}
              thinkingEnabled={thinkingEnabled}
            />
          ))
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
              placeholder="输入消息..."
              rows={1}
              disabled={isGenerating}
            />
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

function Message({ message, thinkingEnabled }) {
  const [thinkingExpanded, setThinkingExpanded] = useState(true)
  const isUser = message.role === 'user'

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

        {!isUser && message.tool_calls?.length > 0 && (
          <div className="tool-use">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
            </svg>
            {message.tool_calls.join(', ')}
          </div>
        )}

        <div className={`message-body ${isUser ? 'user-bubble' : 'assistant-text'}`}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        </div>
      </div>
    </div>
  )
}

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
    { title: '快速排序', desc: 'Python 实现并解释时间复杂度', text: '用Python实现快速排序算法' },
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