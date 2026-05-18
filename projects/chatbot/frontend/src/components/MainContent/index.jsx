import { useState, useEffect, useMemo, useRef } from 'react'
import Message from '../Message'
import WelcomeScreen from '../WelcomeScreen'
import {
  apiCreateSquareLink,
  apiDeleteSquareLink,
  apiListAiNews,
  apiListSquareLinks,
  apiRefreshAiNews,
  apiUpdateSquareLink
} from '../../api'
import './styles.css'

const INITIAL_VISIBLE_MESSAGES = 80
const MESSAGE_PAGE_SIZE = 80

function normalizeUrl(rawUrl) {
  const trimmed = rawUrl.trim()
  if (!trimmed) return ''
  if (trimmed.startsWith('/')) return trimmed
  if (/^https?:\/\//i.test(trimmed)) return trimmed
  return `https://${trimmed}`
}

export default function MainContent({
  chat,
  activeView,
  isGenerating,
  thinkingEnabled,
  onSendMessage,
  onUploadFile,
  onStopGeneration,
  onToggleThinking,
  onToggleSidebar,
  isAuthenticated,
  authToken,
  authUser,
  onLoginClick,
  onOpenToolConfig,
  onOpenMcpConfig,
  onOpenSkillConfig
}) {
  const [inputValue, setInputValue] = useState('')
  const [isUploading, setIsUploading] = useState(false)
  const [uploadedFiles, setUploadedFiles] = useState([])
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE_MESSAGES)
  const [squareLinks, setSquareLinks] = useState([])
  const [squareLoading, setSquareLoading] = useState(false)
  const [squareError, setSquareError] = useState('')
  const [isSquareFormOpen, setIsSquareFormOpen] = useState(false)
  const [editingSquareId, setEditingSquareId] = useState(null)
  const [squareName, setSquareName] = useState('')
  const [squareUrl, setSquareUrl] = useState('')
  const [aiNewsItems, setAiNewsItems] = useState([])
  const [aiNewsLoading, setAiNewsLoading] = useState(false)
  const [aiNewsRefreshing, setAiNewsRefreshing] = useState(false)
  const [aiNewsError, setAiNewsError] = useState('')
  const [aiNewsSelectedDate, setAiNewsSelectedDate] = useState('')
  const [aiNewsSortOrder, setAiNewsSortOrder] = useState('desc')
  const messagesEndRef = useRef(null)
  const fileInputRef = useRef(null)
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

  useEffect(() => {
    if (activeView !== 'square' || !authToken) return
    let cancelled = false
    const loadSquare = async () => {
      try {
        setSquareLoading(true)
        const data = await apiListSquareLinks(authToken)
        if (!cancelled) {
          setSquareLinks(data.links || [])
          setSquareError('')
        }
      } catch (error) {
        if (!cancelled) setSquareError(error.message || '加载链接失败')
      } finally {
        if (!cancelled) setSquareLoading(false)
      }
    }
    loadSquare()
    return () => {
      cancelled = true
    }
  }, [activeView, authToken])

  useEffect(() => {
    if (activeView !== 'ai-news' || !authToken) return
    let cancelled = false
    const loadAiNews = async () => {
      try {
        setAiNewsLoading(true)
        const data = await apiListAiNews(authToken, 80)
        if (!cancelled) {
          setAiNewsItems(data.items || [])
          setAiNewsError('')
        }
      } catch (error) {
        if (!cancelled) setAiNewsError(error.message || '加载 AI 资讯失败')
      } finally {
        if (!cancelled) setAiNewsLoading(false)
      }
    }
    loadAiNews()
    return () => {
      cancelled = true
    }
  }, [activeView, authToken])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (inputValue.trim() && !isUploading) {
      onSendMessage(inputValue, uploadedFiles)
      setInputValue('')
      setUploadedFiles([])
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

  const handleUploadClick = () => {
    if (!isAuthenticated) {
      onLoginClick?.()
      return
    }
    fileInputRef.current?.click()
  }

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return

    if (!isAuthenticated) {
      onLoginClick?.()
      return
    }

    try {
      setIsUploading(true)
      const uploadResult = await onUploadFile?.(file)
      if (uploadResult?.savedPath) {
        setUploadedFiles((prev) => {
          const exists = prev.some((item) => item.savedPath === uploadResult.savedPath)
          if (exists) return prev
          return [...prev, uploadResult]
        })
      }
    } catch (error) {
      console.error('Upload failed:', error)
      alert(`文件上传失败: ${error.message}`)
    } finally {
      setIsUploading(false)
    }
  }

  const removeUploadedFile = (savedPath) => {
    setUploadedFiles((prev) => prev.filter((item) => item.savedPath !== savedPath))
  }

  const handleSquareSubmit = async (e) => {
    e.preventDefault()
    if (!authToken) {
      setSquareError('请先登录')
      return
    }
    const name = squareName.trim()
    const url = normalizeUrl(squareUrl)
    if (!name || !url) {
      setSquareError('请输入名称和有效链接')
      return
    }
    try {
      if (editingSquareId) {
        const data = await apiUpdateSquareLink(authToken, editingSquareId, { name, url })
        setSquareLinks((prev) => prev.map((item) => item.id === editingSquareId ? data.link : item))
      } else {
        const data = await apiCreateSquareLink(authToken, { name, url })
        setSquareLinks((prev) => [data.link, ...prev])
      }
      setSquareName('')
      setSquareUrl('')
      setSquareError('')
      setEditingSquareId(null)
      setIsSquareFormOpen(false)
    } catch (error) {
      setSquareError(error.message || '保存失败')
    }
  }

  const handleSquareEdit = (link) => {
    if (!link.is_mine) return
    setEditingSquareId(link.id)
    setSquareName(link.name)
    setSquareUrl(link.url)
    setSquareError('')
    setIsSquareFormOpen(true)
  }

  const handleSquareDelete = async (link) => {
    if (!link.is_mine || !authToken) return
    try {
      await apiDeleteSquareLink(authToken, link.id)
      setSquareLinks((prev) => prev.filter((item) => item.id !== link.id))
      if (editingSquareId === link.id) {
        setEditingSquareId(null)
        setSquareName('')
        setSquareUrl('')
        setIsSquareFormOpen(false)
      }
    } catch (error) {
      setSquareError(error.message || '删除失败')
    }
  }

  const handleRefreshAiNews = async () => {
    if (!authToken) {
      onLoginClick?.()
      return
    }
    try {
      setAiNewsRefreshing(true)
      await apiRefreshAiNews(authToken)
      const data = await apiListAiNews(authToken, 80)
      setAiNewsItems(data.items || [])
      setAiNewsError('')
    } catch (error) {
      setAiNewsError(error.message || '刷新 AI 资讯失败')
    } finally {
      setAiNewsRefreshing(false)
    }
  }

  const formatNewsTime = (raw) => {
    if (!raw) return '未知时间'
    const ts = Number(raw)
    if (isNaN(ts)) return '未知时间'
    const date = new Date(ts > 1e12 ? ts : ts * 1000)
    return date.toLocaleString('zh-CN', { hour12: false })
  }

  const displayedAiNews = useMemo(() => {
    const normalized = aiNewsItems.filter((item) => {
      const ts = Number(item.published_at)
      if (isNaN(ts)) return false
      const ms = (ts > 1e12 ? ts : ts * 1000)
      if (!aiNewsSelectedDate) return true
      const itemDate = new Date(ms).toISOString().slice(0, 10)
      if (itemDate !== aiNewsSelectedDate) return false
      return true
    })
    return normalized.sort((a, b) => {
      const ta = Number(a.published_at) || 0
      const tb = Number(b.published_at) || 0
      return aiNewsSortOrder === 'asc' ? ta - tb : tb - ta
    })
  }, [aiNewsItems, aiNewsSelectedDate, aiNewsSortOrder])

  const currentChatTitle = activeView === 'square'
    ? '链接广场'
    : (activeView === 'ai-news' ? 'AI 资讯' : (chat?.title || '新对话'))

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

      {activeView === 'square' ? (
        <div className="square-page">
          <div className="square-page-head">
            <h2>项目与文档广场</h2>
            <p>所有用户可见，支持发布链接；仅可编辑或删除自己发布的内容。</p>
          </div>
          <div className="square-page-toolbar">
            <button
              type="button"
              className="square-new-btn"
              onClick={() => {
                if (!isAuthenticated) {
                  onLoginClick?.()
                  return
                }
                setIsSquareFormOpen((prev) => {
                  const next = !prev
                  if (!next) {
                    setEditingSquareId(null)
                    setSquareName('')
                    setSquareUrl('')
                    setSquareError('')
                  }
                  return next
                })
              }}
            >
              {isSquareFormOpen ? '取消' : '+ 发布链接'}
            </button>
          </div>
          {isSquareFormOpen && (
            <form className="square-form" onSubmit={handleSquareSubmit}>
              <input
                className="square-input"
                value={squareName}
                onChange={(e) => setSquareName(e.target.value)}
                placeholder="名称，例如：有趣的 AI Demo"
              />
              <input
                className="square-input"
                value={squareUrl}
                onChange={(e) => setSquareUrl(e.target.value)}
                placeholder="链接，例如：https://example.com 或 /agentdocs/"
              />
              {squareError ? <div className="square-error">{squareError}</div> : null}
              <button className="square-submit-btn" type="submit">
                {editingSquareId ? '更新链接' : '发布链接'}
              </button>
            </form>
          )}
          <div className="square-list">
            {squareLoading ? <div className="square-meta">加载中...</div> : null}
            {!squareLoading && squareLinks.length === 0 ? <div className="square-meta">广场还没有链接，快发布第一条吧。</div> : null}
            {squareLinks.map((link) => (
              <div key={link.id} className="square-card">
                <a href={link.url} target="_blank" rel="noopener noreferrer" className="square-card-title">
                  {link.name}
                </a>
                <div className="square-card-url">{link.url}</div>
                <div className="square-card-bottom">
                  <span className="square-meta">发布者: {link.owner_username || authUser || 'unknown'}</span>
                  {link.is_mine ? (
                    <div className="square-card-actions">
                      <button type="button" className="square-card-btn" onClick={() => handleSquareEdit(link)}>编辑</button>
                      <button type="button" className="square-card-btn danger" onClick={() => handleSquareDelete(link)}>删除</button>
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : activeView === 'ai-news' ? (
        <div className="square-page">
          <div className="square-page-head">
            <h2>AI 资讯</h2>
            <p>每日自动抓取最新 AI 新闻，也可以手动刷新。</p>
          </div>
          <div className="square-page-toolbar">
            <button
              type="button"
              className="square-new-btn"
              onClick={handleRefreshAiNews}
              disabled={aiNewsRefreshing}
            >
              {aiNewsRefreshing ? '刷新中...' : '刷新资讯'}
            </button>
            <div className="ai-news-toolbar-controls">
              <label className="ai-news-control-label">
                选择日期
                <input
                  type="date"
                  className="ai-news-date"
                  value={aiNewsSelectedDate}
                  onChange={(e) => setAiNewsSelectedDate(e.target.value)}
                />
              </label>
              <label className="ai-news-control-label">
                排序
                <select
                  className="ai-news-select"
                  value={aiNewsSortOrder}
                  onChange={(e) => setAiNewsSortOrder(e.target.value)}
                >
                  <option value="desc">新到旧</option>
                  <option value="asc">旧到新</option>
                </select>
              </label>
              <button
                type="button"
                className="ai-news-clear-btn"
                onClick={() => setAiNewsSelectedDate('')}
                disabled={!aiNewsSelectedDate}
              >
                清空日期
              </button>
            </div>
          </div>
          {aiNewsError ? <div className="square-error">{aiNewsError}</div> : null}
          <div className="square-list">
            {aiNewsLoading ? <div className="square-meta">加载中...</div> : null}
            {!aiNewsLoading && displayedAiNews.length === 0 ? <div className="square-meta">当前条件下暂无资讯，可调整日期或点击刷新。</div> : null}
            {displayedAiNews.map((item) => (
              <div key={item.id} className="square-card">
                <a href={item.url} target="_blank" rel="noopener noreferrer" className="square-card-title">
                  {item.title}
                </a>
                <div className="square-card-url">{item.summary || item.url}</div>
                <div className="square-card-bottom">
                  <span className="square-meta">来源: {item.source || 'Unknown'}</span>
                  <span className="square-meta">{formatNewsTime(item.published_at)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <>
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
                <input
                  ref={fileInputRef}
                  type="file"
                  className="upload-input-hidden"
                  onChange={handleFileChange}
                  multiple
                />
                <button
                  type="button"
                  className="upload-btn"
                  onClick={handleUploadClick}
                  disabled={isGenerating || isUploading}
                  title="上传文件"
                >
                  +
                </button>
                <textarea
                  className="input-textarea"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  onInput={autoResize}
                  placeholder={
                    isUploading
                      ? '文件上传并解析中...'
                      : (isAuthenticated ? '输入消息...' : '请先登录后发送消息')
                  }
                  rows={1}
                  disabled={isGenerating || isUploading}
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
                    disabled={isGenerating || isUploading || !inputValue.trim()}
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="12" y1="19" x2="12" y2="5" />
                      <polyline points="5 12 12 5 19 12" />
                    </svg>
                  </button>
                )}
              </div>
              {uploadedFiles.length > 0 && (
                <div className="uploaded-file-list">
                  {uploadedFiles.map((file) => (
                    <div key={file.savedPath} className="uploaded-file-chip">
                      <span className="uploaded-file-name">{file.fileName}</span>
                      <button
                        type="button"
                        className="uploaded-file-remove"
                        onClick={() => removeUploadedFile(file.savedPath)}
                        title="移除文件"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              )}
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
                  <button
                    type="button"
                    className="toolbar-btn"
                    onClick={onOpenToolConfig}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="3" y="3" width="7" height="7" />
                      <rect x="14" y="3" width="7" height="7" />
                      <rect x="14" y="14" width="7" height="7" />
                      <rect x="3" y="14" width="7" height="7" />
                    </svg>
                    工具配置
                  </button>
                  <button
                    type="button"
                    className="toolbar-btn"
                    onClick={onOpenMcpConfig}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="2" y="2" width="20" height="8" rx="2" />
                      <rect x="2" y="14" width="20" height="8" rx="2" />
                      <line x1="6" y1="6" x2="6.01" y2="6" />
                      <line x1="6" y1="18" x2="6.01" y2="18" />
                    </svg>
                    MCP配置
                  </button>
                  <button
                    type="button"
                    className="toolbar-btn"
                    onClick={onOpenSkillConfig}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M14.5 10c-.83 0-1.5-.67-1.5-1.5v-5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5v5c0 .83-.67 1.5-1.5 1.5z" />
                      <path d="M20.5 10H19V8.5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5-.67 1.5-1.5 1.5z" />
                      <path d="M9.5 14c.83 0 1.5.67 1.5 1.5v5c0 .83-.67 1.5-1.5 1.5S8 21.33 8 20.5v-5c0-.83.67-1.5 1.5-1.5z" />
                      <path d="M3.5 14H5v1.5c0 .83-.67 1.5-1.5 1.5S2 16.33 2 15.5 2.67 14 3.5 14z" />
                      <path d="M14 14.5c0-.83.67-1.5 1.5-1.5h5c.83 0 1.5.67 1.5 1.5s-.67 1.5-1.5 1.5h-5c-.83 0-1.5-.67-1.5-1.5z" />
                      <path d="M15.5 19H14v1.5c0 .83.67 1.5 1.5 1.5s1.5-.67 1.5-1.5-.67-1.5-1.5-1.5z" />
                      <path d="M10 9.5C10 8.67 9.33 8 8.5 8h-5C2.67 8 2 8.67 2 9.5S2.67 11 3.5 11h5c.83 0 1.5-.67 1.5-1.5z" />
                      <path d="M8.5 5H10V3.5C10 2.67 9.33 2 8.5 2S7 2.67 7 3.5 7.67 5 8.5 5z" />
                    </svg>
                    Skill配置
                  </button>
                </div>
                <div className="input-hints">
                  <span>Enter 发送 · Shift+Enter 换行</span>
                </div>
              </div>
            </form>
          </div>
        </>
      )}
    </div>
  )
}