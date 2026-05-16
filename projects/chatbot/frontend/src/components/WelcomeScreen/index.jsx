import './styles.css'

const examples = [
  { title: '工具调用', desc: '分开两次调用工具，计算 431*131 结果再乘2', text: '分开两次调用工具，计算 431*131 结果再乘2' },
  { title: '量子计算', desc: '用简单易懂的方式解释', text: '解释量子计算的基本原理' },
  { title: '科技趋势', desc: 'AI、新能源、半导体方向', text: '分析当前科技行业的发展趋势' },
  { title: '书籍推荐', desc: '不同水平阶段的经典书籍', text: '推荐几本提升编程技能的书籍' },
]

export default function WelcomeScreen({ onSendMessage }) {
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