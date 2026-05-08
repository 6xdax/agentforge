# AI Agent 后端部署文档（4G 内存优化版）

适用场景：

* FastAPI
* WebSocket
* 多 Agent
* RAG / 向量检索
* 云服务器部署
* Docker Compose
* 4G 内存服务器

推荐系统：

* Ubuntu 22.04 / 24.04
* 2C4G 起步
* Docker + Docker Compose

---

# 一、最终架构

```text
Internet
    ↓
Nginx
    ↓
FastAPI
    ↓
├── PostgreSQL + pgvector
└── Redis
```

---

# 二、4G 服务器推荐配置

| 服务         | 内存建议      |
| ---------- | --------- |
| PostgreSQL | 512MB     |
| Redis      | 256MB     |
| FastAPI    | 512MB~1GB |
| Nginx      | <100MB    |
| Linux 系统   | 1GB       |
| 预留缓存       | 1GB       |

---

# 三、目录结构

```text
agentforge/
├── app/
│   ├── main.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── ...
│
├── nginx/
│   └── nginx.conf
│
├── data/
│   ├── postgres/
│   └── redis/
│
├── docker-compose.yml
│
└── .env
```

---

# 四、安装 Docker

## 1. 更新系统

```bash
sudo apt update && sudo apt upgrade -y
```

---

## 2. 安装 Docker

```bash
curl -fsSL https://get.docker.com | sh
```

---

## 3. 启动 Docker

```bash
sudo systemctl enable docker
sudo systemctl start docker
```

---

## 4. 检查 Docker Compose

```bash
docker compose version
```

如果没有：

```bash
sudo apt install docker-compose-plugin -y
```

---

# 五、创建项目目录

```bash
mkdir -p ~/agentforge
cd ~/agentforge
```

---

# 六、创建 FastAPI 项目

## app/main.py

```python
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()


@app.get("/")
async def root():
    return JSONResponse({
        "message": "AgentForge API Running"
    })
```

---

## app/requirements.txt

```text
fastapi
uvicorn[standard]
sqlalchemy
psycopg[binary]
asyncpg
redis
```

---

# 七、创建 Dockerfile

## app/Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD [
    "uvicorn",
    "main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000",
    "--workers",
    "1"
]
```

---

# 八、创建 .env

## .env

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_DB=agentforge
```

---

# 九、创建 docker-compose.yml（4G 优化版）

## docker-compose.yml

```yaml
services:

  postgres:
    image: pgvector/pgvector:pg17

    container_name: postgres

    restart: unless-stopped

    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}

    command:
      - "postgres"
      - "-c"
      - "shared_buffers=256MB"
      - "-c"
      - "effective_cache_size=512MB"
      - "-c"
      - "maintenance_work_mem=64MB"
      - "-c"
      - "work_mem=4MB"
      - "-c"
      - "max_connections=50"

    mem_limit: 700m

    volumes:
      - ./data/postgres:/var/lib/postgresql/data

    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"


  redis:
    image: redis:7

    container_name: redis

    restart: unless-stopped

    command:
      - redis-server
      - --appendonly
      - "yes"
      - --maxmemory
      - "256mb"
      - --maxmemory-policy
      - "allkeys-lru"

    mem_limit: 300m

    volumes:
      - ./data/redis:/data

    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"


  fastapi:
    build:
      context: ./app

    container_name: fastapi

    restart: unless-stopped

    depends_on:
      postgres:
        condition: service_healthy

    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      REDIS_URL: redis://redis:6379

    command:
      [
        "uvicorn",
        "main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--workers",
        "1"
      ]

    mem_limit: 1200m

    volumes:
      - ./app:/app

    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"


  nginx:
    image: nginx:latest

    container_name: nginx

    restart: unless-stopped

    depends_on:
      - fastapi

    ports:
      - "80:80"

    mem_limit: 100m

    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro

    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

---

# 十、创建 Nginx 配置

## nginx/nginx.conf

```nginx
events {}

http {

    upstream fastapi_backend {
        server fastapi:8000;
    }

    server {

        listen 80;

        client_max_body_size 100m;

        location / {

            proxy_pass http://fastapi_backend;

            proxy_http_version 1.1;

            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;

            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }
}
```

---

# 十一、启动服务

## 构建并启动

```bash
docker compose up -d --build
```

---

## 查看状态

```bash
docker compose ps
```

---

## 查看日志

```bash
docker compose logs -f
```

---

## 查看 FastAPI 日志

```bash
docker compose logs -f fastapi
```

---

# 十二、验证服务

浏览器访问：

```text
http://你的服务器IP
```

返回：

```json
{
  "message": "AgentForge API Running"
}
```

说明部署成功。

---

# 十三、启用 pgvector

进入 PostgreSQL：

```bash
docker exec -it postgres psql -U postgres
```

执行：

```sql
CREATE EXTENSION vector;
```

查看：

```sql
\dx
```

如果看到：

```text
vector
```

说明成功。

---

# 十四、FastAPI 连接 PostgreSQL

```python
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = (
    "postgresql+asyncpg://postgres:your_password@postgres:5432/agentforge"
)

engine = create_async_engine(
    DATABASE_URL,
    echo=True
)
```

---

# 十五、FastAPI 连接 Redis

```python
import redis.asyncio as redis

client = redis.from_url(
    "redis://redis:6379",
    decode_responses=True
)
```

---

# 十六、开启 Swap（4G 必做）

## 创建 4G swap

```bash
sudo fallocate -l 4G /swapfile
```

---

## 设置权限

```bash
sudo chmod 600 /swapfile
```

---

## 创建 swap

```bash
sudo mkswap /swapfile
```

---

## 启用 swap

```bash
sudo swapon /swapfile
```

---

## 开机自动挂载

```bash
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

## 查看内存

```bash
free -h
```

---

# 十七、安装监控工具

## 安装 htop

```bash
sudo apt install htop -y
```

---

## 查看系统资源

```bash
htop
```

---

## 查看 Docker 内存

```bash
docker stats
```

---

# 十八、生产环境建议

---

# 1. 不暴露 PostgreSQL

生产环境建议删除：

```yaml
ports:
  - "5432:5432"
```

---

# 2. 不暴露 Redis

生产环境建议删除：

```yaml
ports:
  - "6379:6379"
```

---

# 3. 使用 HTTPS

推荐：

* Let's Encrypt
* Certbot

后续：

```text
Nginx + HTTPS
```

即可。

---

# 4. worker 不要超过 1

4G 内存：

```text
uvicorn workers=1
```

最稳。

---

# 5. 不要部署这些服务

4G 禁止：

| 服务            | 原因   |
| ------------- | ---- |
| Elasticsearch | 太吃内存 |
| Kafka         | 太重   |
| Milvus        | 太重   |
| ClickHouse    | 太重   |
| Ollama 大模型    | 顶不住  |

---

# 十九、推荐后续扩展

以后升级 8G 后可增加：

| 服务                | 作用       |
| ----------------- | -------- |
| Celery / Dramatiq | 后台任务     |
| MinIO             | 文件存储     |
| Prometheus        | 监控       |
| Grafana           | 可视化      |
| Loki              | 日志       |
| Traefik           | 自动 HTTPS |

---

# 二十、推荐最终生产架构

```text
Nginx
  ↓
FastAPI
  ↓
Redis
PostgreSQL + pgvector
```

适合：

* AI Agent
* WebSocket
* 多用户聊天
* RAG
* 工作流系统
* 小型 SaaS

这是目前 4G 云服务器较稳定的一套 AI 后端架构。
