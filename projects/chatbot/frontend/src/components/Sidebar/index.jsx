import { useState } from 'react'
import './styles.css'

export default function Sidebar({
  chats,
  currentChatId,
  onSwitchChat,
  onDeleteChat,
  onNewChat,
  isOpen,
  authUser,
  onLogout,
  onLoginClick,
  onRegisterClick
}) {
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
        <a className="docs-entry-btn" href="/docs/" target="_blank" rel="noopener noreferrer">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
            <polyline points="10 9 9 9 8 9" />
          </svg>
          文档中心
        </a>
        <a className="docs-entry-btn agent-framework-btn" href="/agentdocs/" target="_blank" rel="noopener noreferrer">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="3" />
            <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83" />
          </svg>
          Agent 框架
        </a>
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