import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import './styles.css'

export default function ThinkingIndicator({ thinking, completed, expanded, onToggle }) {
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