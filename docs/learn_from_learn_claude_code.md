# 从 Learn Claude Code 可以学到什么

这篇文档不是复述原项目内容，而是提炼它对 AgentForge 的直接启发。

参考项目：
https://github.com/shareAI-lab/learn-claude-code/blob/main/README-zh.md

## 一句话结论

最值得学的不是某个技巧，而是一个清晰的工程边界：

Agent 的智能来自模型，工程代码的职责是构建 harness。

放到 AgentForge 里，这句话可以翻译成：

- agentcore 负责最小 agent runtime
- tools、skills、memory、mcps 负责把模型放进一个可工作的环境
- 项目外围模块的价值，不是替模型做决策，而是给模型更好的观察、行动、知识和边界

## 1. 先把心智模型摆正

参考项目最重要的观点，是把“开发 Agent”改写成“开发 Harness”。

这个视角对 AgentForge 很关键，因为它能直接回答一个经常会出现的架构问题：

哪些东西应该放进 agentcore，哪些东西不应该？

如果沿着 harness 思路来划分，边界会很清楚。

应该放进 agentcore 的：

- agent loop
- provider 协议与最小模型调用接口
- tool registry 与调度
- memory backend 协议与最小实现
- 基础错误处理
- 最小 schema validation 能力

不应该放进 agentcore 的：

- 具体业务工具
- MCP 适配器
- skills 文件与加载策略
- 复杂任务编排
- 团队协作、多 agent 邮箱、后台任务等高级机制
- 具体领域知识库

这个划分的价值在于，agentcore 变成“稳定内核”，而不是“什么都想装进去的小框架”。

## 2. 最小循环要稳定，外层机制再逐层叠加

参考项目非常强调一个最小循环：

- 把消息发给模型
- 模型决定是否调用工具
- 如果调用工具，就执行并把结果追加回上下文
- 如果不调用工具，就结束当前轮次

这对 AgentForge 的启发是：

核心循环应该尽量小、尽量稳定、尽量少改。

新能力最好不要通过不断改写 agent loop 来实现，而应该通过外围机制叠加：

- 加工具，不改循环
- 加知识加载，不改循环
- 加上下文压缩，不改循环
- 加任务系统，不改循环
- 加子 agent，不改循环

这也是为什么 agentcore 当前的定位是合理的。它应该像一个小内核，外围能力围绕它组装，而不是不断把实验机制写进 core。

## 3. 真正重要的不是“更多提示词”，而是更好的环境

参考项目反复强调，工程师的工作不是编写智能，而是给智能提供工作环境。

对 AgentForge 来说，这个环境可以拆成五类资产：

- Tools：文件、终端、网络、数据库、浏览器、MCP
- Knowledge：文档、规范、架构决策、API 说明、技能文件
- Observation：错误、日志、git diff、任务状态、运行结果
- Action Interface：命令执行、文件修改、API 调用、异步任务
- Permissions：沙箱、审批、信任边界、只读/可写范围

这个分类很适合直接拿来做 AgentForge 的模块规划：

- agentcore：Loop + Tool Registry + Provider + Memory 协议
- tools：通用工具集合
- skills：按需加载的知识/操作指南
- memory：core 之外的更强 memory backend
- mcps：MCP 客户端和适配层

这比按“功能越来越多”来堆模块更清晰，因为每一类模块都对应 agent 的一种工作条件。

## 4. 技能和知识应该按需加载，不要默认塞满 system prompt

参考项目很强调一个点：知识不是越多越好，而是越相关越好。

这对 AgentForge 的直接启发是：

- skills 不应该被设计成一个大而全的固定 prompt 包
- 更合理的方式是让 agent 知道“有哪些知识可用”，需要时再加载
- tool_result、文件读取、知识检索，比预先把大量内容塞进 system prompt 更稳

这意味着以后如果 AgentForge 做 skills 模块，最好把它设计成：

- 可枚举
- 可发现
- 可按需读取
- 可组合

而不是做成一个巨大的默认上下文模板。

## 5. 上下文管理会成为框架升级的分水岭

参考项目给出的进阶路径里，有几个能力很值得 AgentForge 后续吸收：

- 子任务隔离上下文
- 上下文压缩
- 任务持久化
- 后台任务
- 多 agent 协作
- worktree 隔离

这些能力的共同点是：它们不是“更聪明的 prompt”，而是“更成熟的运行环境”。

对 AgentForge 而言，最自然的演进顺序大概是：

1. 保持 agentcore 极小且稳定
2. 在外围先补计划与任务持久化
3. 再补 skills 按需加载
4. 再补上下文压缩与子 agent
5. 最后再考虑后台任务、团队协作、目录隔离

这个顺序有一个现实好处：每一步都能独立验证，不会把 core 弄得越来越脆。

## 6. 课程化、递进式架构很值得借鉴

参考项目把能力拆成 s01 到 s12 的递进教学，这种组织方式值得学。

对 AgentForge 来说，这不一定要照搬成“12 课”，但至少应该吸收两个原则：

- 每个新机制只解决一个问题
- 每个机制都能独立演示、独立运行、独立验证

这意味着后面新增模块时，最好避免“大一统 demo”，而是拆成一组小而清楚的例子：

- loop 最小示例
- tools 示例
- memory 示例
- skill 加载示例
- task system 示例
- mcp 接入示例

这样文档、教学和调试成本都会明显下降。

## 7. 先明确范围，避免把教学项目伪装成生产系统

参考项目有一个很成熟的做法，就是明确写出“哪些东西故意没做”。

这对 AgentForge 很有帮助，因为当前项目正处于从最小 demo 向可扩展框架过渡的阶段。这个时候最怕的是：

- 文档写得像生产系统
- 实际上只是教学版最小实现
- 用户误以为已经包含完整权限、生命周期、恢复、MCP 运行时等能力

AgentForge 也应该在文档里明确声明范围，例如：

- agentcore 当前是最小 runtime，不是完整生产 agent platform
- tools、skills、mcps、memory 扩展仍在外围演进
- 权限治理、恢复/fork、异步任务编排、多 agent 协作等属于后续机制

这会让整个项目显得更诚实，也更专业。

## 8. 对 AgentForge 的最直接路线图启发

如果把参考项目的经验翻译成 AgentForge 的短中期路线，可以得到一个非常清楚的版本。

### 核心层：agentcore

保持极小，只做以下事情：

- Agent loop
- Provider protocol
- Tool registry
- Memory backend protocol
- 最小 memory 实现
- 基础错误模型
- Schema validation

### 第一圈扩展：项目内基础模块

优先补这几类：

- tools：文件、shell、http 等通用工具
- skills：按需加载的知识片段与操作约束
- memory：core 之外的持久化 memory backend
- mcps：MCP server/client 接入适配

### 第二圈扩展：更强运行机制

等第一圈稳定后，再考虑：

- task system
- subagent
- context compaction
- background tasks
- team coordination
- workspace/worktree isolation

这个路线最大的好处是：每一层的职责都清楚，不会让 agentcore 膨胀成“大杂烩”。

## 9. 对当前仓库最值得立即吸收的三件事

如果只选最值得现在就做的三件事，我建议是：

1. 在 docs 中单独写清楚“agentcore 是 core，tools/skills/mcps/memory 是 harness 扩展”
2. 给未来扩展模块设计按需加载接口，而不是默认耦合进 core
3. 用递进示例替代单个大示例，把每个机制都做成独立可运行脚本

这三件事都不大，但会明显提升项目的清晰度。

## 10. 最后的判断

参考项目最大的价值，不是告诉我们“Claude Code 有哪些功能”，而是告诉我们应该把工程精力放在哪里。

对 AgentForge 来说，最值得吸收的结论只有一句：

不要试图在 agentcore 里“制造智能”，而要在 AgentForge 的外围模块里“建设环境”。

模型负责决策。

harness 负责让决策可观察、可执行、可约束、可扩展。

这才是 AgentForge 最应该坚持的产品边界。