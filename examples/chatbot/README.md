# AgentForge Chatbot

基于 FastAPI 的聊天机器人后端，使用 Supervisor 管理进程。

## 目录结构

```
chatbot/
├── backend/
│   ├── main.py          # FastAPI 应用
│   └── static/
│       └── index.html  # 前端页面
└── supervisor/
    └── agentforge.conf  # Supervisor 配置
```

## 快速启动

### 1. 安装依赖

```bash
cd /home/ubuntu/workspace/agentforge
pip install fastapi uvicorn python-dotenv
```

### 2. 直接运行（开发模式）

```bash
cd /home/ubuntu/workspace/agentforge/examples/chatbot/backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000 查看聊天界面。

### 3. 使用 Supervisor 管理

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
| `/api/chat` | GET | 简单 GET 查询 (`?q=内容`) |
| `/api/chat` | POST | POST 发送消息 |
| `/ws/chat` | WebSocket | WebSocket 实时聊天 |

### REST API 示例

```bash
# GET 请求
curl "http://localhost:8000/api/chat?q=hello"

# POST 请求
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "hello"}'
```

### WebSocket 示例

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/chat");
ws.send(JSON.stringify({ message: "Hello!" }));
ws.onmessage = (event) => console.log(JSON.parse(event.data));
```

## Demo Tools

已注册的示例工具：

- `echo` - 回显消息
- `get_time` - 获取当前时间

## Supervisor 管理命令

```bash
sudo supervisorctl status agentforge-chatbot   # 查看状态
sudo supervisorctl stop agentforge-chatbot     # 停止
sudo supervisorctl start agentforge-chatbot     # 启动
sudo supervisorctl restart agentforge-chatbot   # 重启
sudo supervisorctl reread                       # 重新读取配置
sudo supervisorctl update                      # 更新配置
```