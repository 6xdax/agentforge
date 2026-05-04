# 设计哲学：最小内核，最大灵活性

## 核心理念

AgentForge 的核心包 agentcore 遵循一个简单而坚定的原则：**只实现最核心的东西，其他一切通过扩展实现**。

这不是功能缺失，而是有意为之的克制。

---

## 与 pi-mono 的殊途同归

pi-mono 是 badlogic（libgdx 作者）开源的 TypeScript Agent 框架，采用完全相同的设计哲学：

| | pi-mono | agentcore |
|--|---------|-----------|
| 核心代码量 | ~400 行 TypeScript | ~120 行 Python |
| 扩展方式 | npm 包组合 | pip 包组合 |
| 内置工具 | **零** | **零** |
| LLM 提供商 | 按需安装 | 按需注入 |
| 用户按需组装 | ✅ | ✅ |

两者独立设计，却走向了同样的结论——**最小内核 + 按需扩展**是 Agent 框架的最佳起点。

---

## 设计模式

### 1. Protocol（协议）而非继承

```python
class LLMProvider(Protocol):
    def chat(self, messages: list[dict]) -> str: ...
```

用户实现自己的 Provider，不依赖任何基类。Python 的结构化类型检查（Protocol）让接口清晰且无侵入。

### 2. 自注册模式

```python
registry.register(name="calc", schema={...}, handler=calculator)
```

工具在运行时注册，不需要装饰器或继承。**注册者完全掌控自己的代码生命周期。**

### 3. 依赖注入

```python
class Agent:
    def __init__(
        self,
        provider: LLMProvider,
        registry: ToolRegistry,
        memory: Memory | None = None,
    ): ...
```

Agent 本身不创建依赖，外部注入。这让每个组件都可以独立测试和替换。

### 4. 零强制依赖

```toml
[project]
dependencies = []
```

核心包不依赖任何外部库。用户按需安装，**不为我不需要的功能买单**。

---

## 为什么重复造轮子是合理的

### 学习角度

只有亲手实现一遍，才能真正理解 Agent 的核心机制：

- 工具如何被调度
- 记忆如何影响上下文
- LLM 调用循环如何工作
- 错误如何被分类和重试

### 面试角度

面试官问："为什么不直接用 LangChain？"

> "LangChain 是一个功能完整的框架，但它的设计追求大而全。
> 我做 agentcore 不是为了替代它，而是为了彻底理解 Agent 的本质。
> 120 行代码，我可以向面试官逐行讲解。LangChain 你敢吗？"

更深的回答：

> "pi-mono 的作者 badlogic（libgdx、libgdx-json 的作者）也选择了同样的设计思路。
> 这不是标新立异，而是和业内资深开发者的理念一致。"

### 实用角度

对于轻量任务，LangChain 太重了：

```
# LangChain 方式
from langchain.agents import Agent
from langchain.tools import Tool
from langchain.memory import ConversationBufferMemory
# ... 50 行配置

# agentcore 方式
from agentcore import Agent, ToolRegistry
registry = ToolRegistry()
registry.register(name="calc", handler=calculator)
agent = Agent(provider=my_provider, registry=registry)
# 5 行，核心相同
```

**简单任务用简单工具。** 不是每个任务都需要全套框架。

---

## 实际对比

### 完成同一个任务

| 维度 | LangChain | agentcore |
|------|-----------|-----------|
| 安装大小 | ~200MB | 0KB（无依赖） |
| 核心代码 | 难以计数 | ~120 行 |
| 配置项 | 数十个 | 3 个（provider, registry, memory） |
| 定制方式 | 继承/覆盖 | 替换整个组件 |
| 可解释性 | 低 | 高 |
| 学习曲线 | 陡峭 | 平缓 |

### 当你需要扩展时

**LangChain 的问题：**
- 扩展点藏在框架深处
- 需要阅读大量源码才能找到切入点
- 版本升级可能破坏定制

**agentcore 的优势：**
- 核心代码可以全部读完
- 任何组件都可以直接替换
- 没有隐藏的魔法，只有显式的设计

---

## 影响力参考

这种设计不是孤例，而是业界共识：

| 项目 | 作者 | 设计选择 |
|------|------|----------|
| pi-mono | badlogic（libgdx） | 400 行核心，npm 包扩展 |
| Click | Pallets | 最小 CLI 框架，按需添加命令 |
| FastAPI | Sebastián Ramírez | 最小 API 框架，依赖注入 |
| Ruff | Astral | 100x 快的 linter，替代 rule-by-rule |

**共同点：核心极简，扩展丰富，社区共建生态。**

---

## 总结

agentcore 的设计选择不是偷懒，而是深思熟虑：

1. **120 行核心** — 任何人都可以完全理解
2. **零依赖** — 按需安装，不捆绑不需要的功能
3. **可替换组件** — Provider、Registry、Memory 都可以独立替换
4. **按需扩展** — 用户选择需要的工具包，不被迫接受全部

> "框架应该像乐高：提供有限的、精心设计的积木，让用户建造自己需要的东西。
> 而不是提供一艘已经造好的船，告诉用户你只需要学会驾驶它。"

这就是 AgentForge 中 agentcore 的设计哲学。
