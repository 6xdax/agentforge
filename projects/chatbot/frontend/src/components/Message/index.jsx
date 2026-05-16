import { memo, useState, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import ThinkingIndicator from '../ThinkingIndicator'
import './styles.css'

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
        {!isUser && message.thinking && (thinkingEnabled || message.thinkingCompleted) && (
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

export default Message