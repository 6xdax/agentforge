import { useState, useEffect, useRef } from 'react'
import Message from '../Message'
import WelcomeScreen from '../WelcomeScreen'
import './styles.css'

const INITIAL_VISIBLE_MESSAGES = 80
const MESSAGE_PAGE_SIZE = 80

export default function MainContent({
  chat,
  isGenerating,
  thinkingEnabled,
  onSendMessage,
  onStopGeneration,
  onToggleThinking,
  onToggleSidebar,
  isAuthenticated
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
            {visibleMessages.filter(Boolean).map((msg, idx) => (
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