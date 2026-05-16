import { useState } from 'react'
import './styles.css'

export default function AuthModal({ mode, onModeSwitch, onSubmit, loading, error }) {
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