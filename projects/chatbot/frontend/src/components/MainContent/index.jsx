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
  onUploadFile,
  onStopGeneration,
  onToggleThinking,
  onToggleSidebar,
  isAuthenticated,
  onLoginClick
}) {
  const [inputValue, setInputValue] = useState('')
  const [isUploading, setIsUploading] = useState(false)
  const [uploadedFiles, setUploadedFiles] = useState([])
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE_MESSAGES)
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
              <button type="button" className="toolbar-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="7" height="7" />
                  <rect x="14" y="3" width="7" height="7" />
                  <rect x="14" y="14" width="7" height="7" />
                  <rect x="3" y="14" width="7" height="7" />
                </svg>
                工具配置
              </button>
              <button type="button" className="toolbar-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="2" y="2" width="20" height="8" rx="2" />
                  <rect x="2" y="14" width="20" height="8" rx="2" />
                  <line x1="6" y1="6" x2="6.01" y2="6" />
                  <line x1="6" y1="18" x2="6.01" y2="18" />
                </svg>
                MCP配置
              </button>
              <button type="button" className="toolbar-btn">
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
    </div>
  )
}