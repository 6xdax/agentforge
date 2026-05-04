# AgentForge Chatbot

基于 FastAPI + React 的聊天机器人，前后端分离架构。

## 目录结构

```
chatbot/
├── backend/
│   └── main.py              # FastAPI 后端 (端口 8000)
├── frontend/
│   ├── src/                 # React 源码
│   ├── dist/                # 构建输出
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
└── supervisor/
    └── agentforge.conf      # Supervisor 配置
```

## 快速启动

### 1. 安装后端依赖

```bash
cd /home/ubuntu/workspace/agentforge
uv pip install fastapi uvicorn python-dotenv
```

### 2. 前端开发 (热更新)

```bash
cd examples/chatbot/frontend
npm install
npm run dev
```

访问 http://localhost:5173 (Vite 开发服务器)，API 请求会自动代理到后端。

### 3. 前端构建 (生产部署)

```bash
cd examples/chatbot/frontend
npm run build
```

构建输出到 `frontend/dist/`

### 4. 后端启动

```bash
cd examples/chatbot/backend
PYTHONPATH=../../src uvicorn main:app --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000 查看聊天界面（后端直接服务前端静态文件）。

### 5. 使用 Supervisor 管理

```bash
# 安装 supervisor（如果还没安装）
sudo apt install supervisor

# 复制配置到 supervisor 目录
sudo cp /home/ubuntu/workspace/agentforge/examples/chatbot/supervisor/agentforge.conf /etc/supervisor/conf.d/

# 重新读取配置并启动
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start agentforge-chatbot

# 查看状态
sudo supervisorctl status agentforge-chatbot

# 查看日志
sudo tail -f /tmp/agentforge-chatbot-stdout.log
```

## API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 前端页面 |
| `/api/chat` | POST | 发送消息 (流式/非流式) |
| `/api/usage` | GET | Token 使用统计 |
| `/ws/chat` | WebSocket | WebSocket 实时聊天 |

### REST API 示例

```bash
# POST 请求 (流式)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "hello", "thinking": true, "stream": true}'

# POST 请求 (非流式)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "hello", "thinking": false, "stream": false}'
```

### WebSocket 示例

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/chat");
ws.send(JSON.stringify({ message: "Hello!", thinking: true, stream: true }));
ws.onmessage = (event) => console.log(JSON.parse(event.data));
```

## 功能特性

- **思考模式** - 显示 AI 推理过程（可展开/收起）
- **流式输出** - 实时显示生成内容
- **工具调用** - 支持 calculator 等工具
- **历史会话** - 本地存储对话历史
- **多会话管理** - 创建/切换/删除会话

## Demo Tools

已注册的示例工具：

- `calculator` - 数学计算
- `echo` - 回显消息
- `get_time` - 获取当前时间
- `file_ops` - 文件操作

## Supervisor 管理命令

```bash
sudo supervisorctl status agentforge-chatbot   # 查看状态
sudo supervisorctl stop agentforge-chatbot    # 停止
sudo supervisorctl start agentforge-chatbot    # 启动
sudo supervisorctl restart agentforge-chatbot # 重启
```
