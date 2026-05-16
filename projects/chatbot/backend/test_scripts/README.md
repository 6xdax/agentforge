# 用户系统测试脚本

此目录包含用户身份验证和会话隔离系统的测试脚本。

## 测试脚本

### 1. `test_auth.py` - 身份验证测试
测试用户注册、登录和Token管理。

**测试内容：**
- 用户注册（成功和重复预防）
- 密码验证（正确、错误和不存在的用户）
- Token生成和验证
- Token过期

**运行：**
```bash
python3 test_auth.py
```

### 2. `test_session.py` - 会话和历史测试
测试每个用户的会话隔离和消息历史持久化。

**测试内容：**
- 每个用户的会话创建
- 用户之间的消息历史隔离
- 跨会话重建的消息持久化
- 历史限制参数

**运行：**
```bash
python3 test_session.py
```

### 3. `test_api_integration.py` - API集成测试
使用真实请求测试完整的HTTP API端点。**需要后端服务器正在运行。**

**测试内容：**
- 用户注册端点
- 用户登录端点
- 聊天认证需求
- 使用有效token的聊天
- 历史认证需求
- 使用有效token的历史检索
- 不同用户之间的消息隔离

**前置条件：**
1. 启动后端服务器：
   ```bash
   cd /home/ubuntu/workspace/agentforge/projects/chatbot/backend
   PYTHONPATH=/home/ubuntu/workspace/agentforge:/home/ubuntu/workspace/agentforge/src:/home/ubuntu/workspace/agentforge/projects/chatbot/backend \
     python3 -m uvicorn main:app --host 0.0.0.0 --port 9000
   ```

2. 在另一个终端中运行测试：
   ```bash
   python3 test_api_integration.py
   ```

## 运行所有测试

### 选项1：单独运行测试
```bash
cd /home/ubuntu/workspace/agentforge/projects/chatbot/backend/test_scripts

# 按顺序运行
python3 test_auth.py
python3 test_session.py

# 在单独的终端中，启动服务器后运行
python3 test_api_integration.py
```

### 选项2：使用测试运行器
```bash
# 运行所有本地测试（不需要服务器）
python3 run_local_tests.py
```

## 测试覆盖范围

| 功能 | test_auth.py | test_session.py | test_api_integration.py |
|-----|-------------|-----------------|----------------------|
| 用户注册 | ✓ | - | ✓ |
| 密码验证 | ✓ | - | ✓ |
| Token生成 | ✓ | - | ✓ |
| Token验证 | ✓ | - | ✓ |
| Token过期 | ✓ | - | - |
| 会话创建 | - | ✓ | ✓ |
| 消息隔离 | - | ✓ | ✓ |
| 历史持久化 | - | ✓ | ✓ |
| API认证 | - | - | ✓ |
| API授权 | - | - | ✓ |

## 预期输出示例

### 成功的测试运行
```
============================================================
测试认证系统
============================================================
测试用户注册...
  ✓ 用户注册成功
  ✓ 拒绝重复用户
测试密码验证...
  ✓ 有效密码通过验证
  ✓ 无效密码被拒绝
  ✓ 不存在的用户被拒绝
测试Token生成和验证...
  ✓ Token生成成功
  ✓ Token验证正确
  ✓ 无效Token被拒绝
  ✓ 被篡改的Token被拒绝
测试Token过期...
  ✓ 新Token有效
  ✓ 过期Token被拒绝

============================================================
所有认证测试通过！✓
============================================================
```

## 注意事项

- `test_auth.py`使用与后端相同的auth模块（从父目录导入）
- `test_session.py`创建单独的测试数据库以避免冲突
- `test_api_integration.py`需要requests库：`pip install requests`
- 测试数据库会自动清理（可通过`CLEANUP_DBS`变量禁用）
- 默认认证密钥是"dev-secret-change-me" - 在生产环境中通过`AGENTFORGE_AUTH_SECRET`环境变量更改

## 疑难解答

### ModuleNotFoundError
确保您从test_scripts目录运行，或者父目录在PYTHONPATH中。

### 服务器连接被拒绝
确保后端服务器在`localhost:9000`上运行：
```bash
cd ../
PYTHONPATH=/home/ubuntu/workspace/agentforge:/home/ubuntu/workspace/agentforge/src:/home/ubuntu/workspace/agentforge/projects/chatbot/backend \
  python3 -m uvicorn main:app --host 0.0.0.0 --port 9000
```

### 数据库被锁定
如果您遇到"数据库已锁定"错误：
- 停止任何正在运行的测试
- 删除旧数据库文件：`rm db/*.db`
- 重新启动测试

## 未来改进

- [ ] 添加并发用户访问的压力测试
- [ ] 添加具有许多消息的历史记录的负载测试
- [ ] 为流式聊天端点添加测试
- [ ] 添加Token刷新机制的测试
- [ ] 与CI/CD管道的集成
