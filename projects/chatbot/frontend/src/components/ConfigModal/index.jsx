import { useEffect, useMemo, useState } from 'react'
import './styles.css'

const TABS = [
  { key: 'tools', label: '工具配置' },
  { key: 'mcp', label: 'MCP配置' },
  { key: 'skills', label: 'Skill配置' }
]

function ConfigList({
  items,
  loading,
  saving,
  onToggle,
  onSave,
  emptyText,
  saveText = '保存配置'
}) {
  if (loading) {
    return <div className="config-modal-empty">加载中...</div>
  }

  if (!items.length) {
    return <div className="config-modal-empty">{emptyText}</div>
  }

  return (
    <>
      <div className="config-modal-list">
        {items.map((item) => (
          <label key={item.name} className="config-modal-item">
            <input
              type="checkbox"
              checked={item.enabled}
              onChange={(e) => onToggle(item.name, e.target.checked)}
            />
            <div className="config-modal-item-main">
              <div className="config-modal-item-title">{item.name}</div>
              {item.description && (
                <div className="config-modal-item-desc">{item.description}</div>
              )}
            </div>
          </label>
        ))}
      </div>
      <div className="config-modal-actions">
        <button
          type="button"
          className="config-modal-save-btn"
          disabled={saving}
          onClick={onSave}
        >
          {saving ? '保存中...' : saveText}
        </button>
      </div>
    </>
  )
}

export default function ConfigModal({
  visible,
  activeTab,
  onClose,
  onSwitchTab,
  state,
  onToggle,
  onSave
}) {
  const [error, setError] = useState('')

  useEffect(() => {
    if (!visible) {
      setError('')
    }
  }, [visible])

  const current = useMemo(() => {
    return state[activeTab] || { items: [], loading: false, saving: false, loaded: false }
  }, [state, activeTab])

  if (!visible) return null

  const handleSave = async () => {
    try {
      setError('')
      await onSave(activeTab)
    } catch (err) {
      setError(err?.message || '保存失败')
    }
  }

  return (
    <div className="config-modal-overlay" onClick={onClose}>
      <div className="config-modal" onClick={(e) => e.stopPropagation()}>
        <div className="config-modal-header">
          <div className="config-modal-title">配置中心</div>
          <button type="button" className="config-modal-close" onClick={onClose}>×</button>
        </div>

        <div className="config-modal-tabs">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`config-modal-tab ${activeTab === tab.key ? 'active' : ''}`}
              onClick={() => onSwitchTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="config-modal-body">
          {error && <div className="config-modal-error">{error}</div>}
          <ConfigList
            items={current.items}
            loading={current.loading}
            saving={current.saving}
            onToggle={(name, enabled) => onToggle(activeTab, name, enabled)}
            onSave={handleSave}
            emptyText="暂无可配置项"
          />
        </div>
      </div>
    </div>
  )
}
