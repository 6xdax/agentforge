https://mp.weixin.qq.com/s/kTfJjEVx_dKRx74TOzh2mQ

面试官问：你的 prompt 缓存命中率多少？
面试官问："你的 prompt 缓存命中率多少？"
"3 年 LLM 应用经验，熟悉 Claude/OpenAI/DeepSeek API，主导过多个 Agent 系统的成本优化"
看到这份简历我问了个简单问题：你线上 Agent 的 prompt cache 命中率是多少？

候选人愣住了。"应该……还行吧？我们用的 Anthropic，文档里写了自动会缓存。"

错。Anthropic 的 prompt caching 必须显式打开，不写 cache_control 就是 0% 命中率。Claude Code 这种产品做到 92% 命中率、省 81% 成本是有方法的；命中率 5% 的团队也大有人在，每个月白白多烧几万块。

prompt caching 是 LLM 应用降本最高效的一个开关。今天这场面试，把这个开关背后的机制讲透。从 KV cache 原理到 5min/1h TTL 的取舍，从「为什么我命中不了」到 Agent 系统怎么榨到 90%+。

 

Round 1：缓存的到底是什么？

面试官："prompt caching 缓存的是什么？为什么能省钱又能加速？"

候选人："就是把之前请求的结果缓存下来，下次同样的 prompt 直接返回？"

正解：

缓存的不是输出文本，而是 Transformer 注意力层里的 Key/Value 张量。 这是 prompt caching 和老式 semantic cache 最根本的区别。

LLM 推理分两个阶段。第一阶段叫 prefill，把输入 prompt 走一遍 Transformer，每一层的注意力都要算出 K、V 矩阵。第二阶段叫 decode，逐 token 生成输出，每生成一个新 token 都要把它的 Q 和前面所有 token 的 K/V 做注意力。prefill 是计算密集型，prompt 越长这一步越贵；decode 是带宽密集型，主要瓶颈在显存搬运。

prompt caching 缓存的就是 prefill 阶段算出来的 K/V。下次请求来了，如果前缀完全一样，K/V 直接从缓存读出，跳过 prefill 这一步。所以省的是算力（钱）和首 token 延迟（time-to-first-token）。输出 token 还是要现算的，价格不变。

价格上的差异有多大？以 DeepSeek V4-flash 为例：cache hit 是 $0.028/M token，cache miss 是 $0.14/M token，差 5 倍。Claude Sonnet 4.6 更夸张，cache read 是 $0.30/M、未缓存输入是 $3.00/M，差 10 倍。延迟上，DeepSeek 公开的数据：128K prompt 命中前缀缓存，首 token 延迟从 13 秒降到 500ms。

这里有个反直觉的点：缓存有非常严格的「前缀匹配」语义。两个 prompt 必须从第 0 个 token 开始字节级一致，才会被认为是同一前缀。哪怕中间多了一个空格、JSON 序列化时 key 顺序变了，缓存就废了。原因是 K/V 编码了精确的位置关系，稍微复用一下别的前缀的 K/V，注意力模式会基于错误的位置信息，产生错误输出。这是数学上的硬约束，不是工程偷懒。

要点速记

- 缓存的是 Transformer 注意力层的 K/V 张量，不是输出文本
- 跳过的是 prefill 阶段，省算力 + 降首 token 延迟
- DeepSeek hit/miss 价差 5 倍，Claude 价差 10 倍
- 必须从第 0 个 token 字节级一致，前缀有任何变化都失效

Round 2：三家 API 的开法不一样

面试官："Claude、OpenAI、DeepSeek 都支持 prompt caching，开法一样吗？"

候选人："应该差不多吧，都是自动开启的。"

（面试官内心 OS）：你这 0% 命中率的根因找到了。

正解：

Anthropic 必须显式标记，OpenAI 和 DeepSeek 自动启用，这是最容易踩的坑。 三家的接口语义、起步门槛、TTL 策略全不一样。

平台      启用方式                起步门槛      TTL 策略
Claude    显式 cache_control     1024 token   5min（默认）/ 1h
OpenAI    自动                   1024 token   5-10min（闲时 1h）
DeepSeek  自动                   64 token     几小时到几天
Claude（Anthropic）：请求里必须加 cache_control 字段，标在你想缓存的内容块上（一般是 system prompt 或 tools 定义）。不加这个字段每次都按全价计费。默认 TTL 是五分钟，要一小时必须再传 ttl: 1h。同一请求可以混用两种 TTL，但长 TTL 必须排在短 TTL 前面。一小时 TTL 的写入价是基础输入价的两倍，需要命中两次以上才能回本。

OpenAI：自动启用无需参数，prompt 长度过千就开始缓存，再以小步长延伸。请求路由基于 prompt 前部 hash，如果想把同一类请求绑到同一台机器，传 prompt_cache_key 参数。注意单 (prefix, cache_key) 的 RPM 上限是十几次每分钟，超了会溢出到多机重新建缓存。TTL 没有显式承诺，闲时最长可保留一小时。

DeepSeek：自动启用无需参数，门槛比 OpenAI 低一个数量级。必须从第 0 个 token 严格匹配。响应里直接返回 prompt_cache_hit_tokens 和 prompt_cache_miss_tokens 字段，监控命中率非常方便。TTL 是 best effort，不保证 100% 命中。

监控字段也不一样。Claude 在 usage 里返回 cache_read_input_tokens 和 cache_creation_input_tokens，再细拆 ephemeral 5min/1h；OpenAI 在 usage.prompt_tokens_details 里返回 cached_tokens；DeepSeek 直接给 hit/miss 两个字段。生产里这几个字段必须画板子监控。

要点速记

- Claude 必须显式 cache_control，不写永远不缓存
- OpenAI 自动开启，门槛过千 token，按小步长延伸
- DeepSeek 自动开启，门槛低、必须从零位严格匹配
- 三家都要监控响应里的 cache 字段，命中率必须有看板

Round 3：为什么命中率只有 5%？

面试官："你们线上命中率多少？如果只有 5% 你会怎么排查？"

候选人："呃……可能 prompt 写得不够稳定？我重新设计一下 system prompt？"

（面试官内心 OS）：连具体的破坏点都说不出来。

正解：

5% 命中率不是 prompt 写得烂，是有东西在偷偷改前缀，而且 90% 的情况你能列出元凶。 给一份生产环境实战的破坏清单。

第一类：时间戳/动态变量混进系统区。 这是最高频的一个坑，几乎每家公司都犯过。常见做法：在 system prompt 第一行写「当前时间是 2026-04-25 14:32:15」、写 session ID、写 user_id。看起来很合理，但每个请求都不一样，哈希到第一个 token 就不同，整段 prompt 永远 cache miss。修复：把这些动态信息塞到最后一条 user message 里，或者用 metadata 字段，永远不要放在系统区。

第二类：JSON/工具定义不稳定序列化。 Python 的 json.dumps() 默认不保证 key 顺序（3.7+ 保证插入顺序，但跨服务依赖可能改）。同一份 tool schema 今天 name 字段在前 desc 在后，明天颠倒过来，前缀就坏了。修复：序列化时强制 sort_keys=True，工具列表的顺序也要固定。

第三类：Cache breakpoint 打在变化的 block 上。 Anthropic 特有的坑。假设你有几个静态块加上最后一块带时间戳的用户消息，你把 cache_control 标在最后一块。结果是：每次都在最后一块写一次新缓存（因为 hash 不同），从来没有读到。回头看前面几块也没建缓存（你没标）。修复：把 cache_control 移到最后一个不变的 block，通常是静态块的末尾。

第四类：模式切换换工具集。 Agent 系统经常做的事：进入 plan 模式时把工具集换成只读集合。直觉对，但工具是缓存前缀的一部分，换工具集等于让整段 prompt 缓存全废。Claude Code 团队的做法很巧：保留所有工具，把 EnterPlanMode 和 ExitPlanMode 本身做成工具，状态切换通过工具调用完成，工具集永远不变。

第五类：往前缀里追加 reminder。 想给模型注入新信息（比如「现在是周三」「文件已修改」），往 system prompt 末尾加一行——前缀变了，缓存全废。Claude Code 的做法：把这种信息塞到下一条 user message 或 tool result 里，用 <system-reminder> 标签包起来。前缀完全不动。

第六类：模型版本悄悄变了。 缓存是模型粒度的。claude-sonnet-4-5 切到 claude-sonnet-4-6，缓存全部失效。生产里换模型版本要做好首批请求全 miss 的预算。

排查方法很简单：读 API response 里的 cache 字段，分别画 hit token 数和 write token 数曲线。命中率突然跌通常是某次部署改了 prompt；常年 0% 通常是上面六类之一。Claude Code 公开数据是九成以上的命中率，单次会话里 lead agent 比 subagent 高十几个点，因为 subagent 第一次调用必走 cold write。

要点速记

- 排查从动态变量开始：时间戳、session ID、user_id 是头号嫌疑
- JSON 序列化必须 sort_keys=True，工具顺序固定
- Anthropic 的 cache_control 标在最后一个不变 block
- 状态切换用工具调用而不是换工具集
- Claude Code 92% 是工业天花板参考

Round 4：5min 还是 1h？

面试官："Claude 的 1h TTL 写入要付 2 倍价格，什么场景值得花这个钱？"

候选人："肯定选便宜的 5min 啊，2 倍太贵了。"

正解：

5min 是默认选项不是更优选项。算清楚损益线，1h 在很多场景反而省更多。

先把账算清楚。Claude 的定价模型可以归纳成下面这张表（基础输入价记作 X）：

项目                 倍率
基础输入             X
5min 缓存写入       1.25 X
1h   缓存写入       2    X
缓存读取             0.1  X
决策核心是写一次能命中几次。

5min 的回本点：写入比基础贵一点二五倍，读取省九成，回本需要命中第二次。也就是五分钟内要被命中两次以上才比不缓存划算。访问频率高于每五分钟一次的场景适用，典型是单用户长对话、客服机器人。

1h 的回本点：写入比基础贵两倍，每次读省九成，需要命中三次以上才能赚。但一小时 TTL 的优势在两点：第一，TTL 长十几倍，跨会话、跨用户分摊机会大很多；第二，访问会刷新 TTL（不重新计费），高频访问下相当于持续保鲜。多用户共享 system prompt 的 Agent 平台、长尾访问的知识库问答，这种场景下一小时几乎一定赚。

有个真实事故可以参考。 Anthropic 在三月初把 Claude Code 的默认 prompt cache TTL 从一小时偷偷下调到五分钟，社区炸锅。用户反馈是同样的工作量配额烧得快了一倍。Anthropic 工程师 Jarred Sumner 的解释是 Claude Code 大量请求是 one-shot，缓存写了用一次就丢，一小时写入价格太亏，相当于每次都付双倍钱。这事的启示：选 TTL 不是看哪个长哪个好，是看你工作负载的读写比。

官方建议的混用策略：同一请求里把不变的身份/规则/few-shot 示例标 1h cache_control，把变化频次稍高的对话上下文标 5min cache_control，前者排在前面。这样长 TTL 段保证基本盘，短 TTL 段灵活演进。代码示例：

messages = [
    {"role": "user", "content": [
        {"type": "text", "text": LONG_SYSTEM_RULES,
         "cache_control": {"type": "ephemeral", "ttl": "1h"}},
        {"type": "text", "text": RECENT_CONTEXT,
         "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": current_question}
    ]}
]
OpenAI 和 DeepSeek 没有 TTL 选项，自动管理几分钟到几小时不等。这两家不需要纠结这个，关键是把请求路由稳住。OpenAI 的 prompt_cache_key 可以把同一类请求路由到同一台机器，但单桶有 RPM 上限，超了就溢出到多机重建缓存。高并发场景需要做哈希分桶。

要点速记

- 5min 命中第二次开始赚，1h 命中第三次开始赚
- 1h 适合多用户共享和长尾访问，5min 适合单用户高频
- 同请求可以混用：身份用 1h，对话用 5min，长 TTL 排在前
- OpenAI 用 prompt_cache_key 控制路由，单桶 RPM 上限要做分桶

Round 5：Agent 系统怎么压到 90%+

面试官："最后一题，给你一个 Agent 系统，怎么把命中率从 50% 拉到 90%+？"

候选人："优化 system prompt？设置长 TTL？"

正解：

90%+ 命中率不是优化 prompt 写出来的，是用工程纪律守出来的。给一份从 50% 拉到 92% 的实操清单。

第一步：把 prompt 拆成「不变区」和「变量区」。 不变区放 system rules、tool definitions、few-shot 示例、长期记忆里稳定的部分。变量区放 user message、retrieved chunks、当前会话状态。cache_control 标在不变区的末尾。一个测试方法：假设这个 prompt 一小时内被发上千次，哪些部分会一字不差？那些就是不变区。

第二步：所有动态信息走「追加」不走「修改」。 想告诉模型「现在是周三」「这个文件刚改过」「用户切到 plan mode 了」？不要去动 system prompt，往下一条 user message 里加一段 <system-reminder> 标签。Codex CLI 和 Claude Code 都是这么做的。前缀永不变，缓存永不破。

第三步：工具集稳定，工具序列化稳定。 工具的添加/删除/重排序都会破坏缓存。生产里把工具集设计成「固定全集」，状态切换通过 EnterXxxMode、ExitXxxMode 这类工具调用完成。JSON 序列化用 sort_keys=True，schema 字段顺序固定。

第四步：长会话用中间断点。 Anthropic 有个细节：超过几十个 content block 的 cache_control 不能都生效，一次只能有四个 active breakpoint。ProjectDiscovery 的做法是每隔十几个 block 打一个 breakpoint，最长支持五十个左右 block 退化前的稳定缓存。这个数字记一下，长 Agent 会话直接抄。

第五步：多 Agent 共享前缀模板。 多 Agent 协作时，subagent 第一次调用必走 cold write（因为路由到不同 worker、缓存独立）。NVIDIA Dynamo 团队公开过四个 Opus subagent 协作做到接近 97% 的聚合命中率，关键是让所有 subagent 共享同一份 system prompt 模板。Claude Code 单 lead agent 比 subagent 高十几个点，差距就是 cold write。

第六步：监控按 stream 切分，不看聚合数。 ProjectDiscovery 公开的踩坑：整体命中率不到七成，但拆开看最近优化路径已经超过 90%。聚合数会骗人。一个低频路径拉低整体，但你优化的全是它，看不出效果。生产监控按 endpoint、按 user segment、按 conversation length 切分。

第七步：把缓存破裂当事故响应。 一次部署改了一个字符，命中率从九成掉到一成，账单第二天就翻倍。Anthropic 工程团队的建议是：cache hit rate 像 SLA 一样监控，掉几个点就告警。

把这七条做完，Claude Code 公开数据九成命中率、八成成本节省，是可复现的工业基线。

要点速记

- 不变区/变量区物理分离，cache_control 标在不变区末尾
- 动态信息走 user message 追加，永远不改 system prompt
- 工具集固定 + 状态用工具调用切换
- 长会话每隔十几个 block 打中间断点
- 监控按 stream 切分，命中率掉几个点就告警
面试官点评
候选人的问题很典型：把 prompt caching 当成「打开就行」的开关，没意识到这是一个需要前缀稳定性、工具稳定性、序列化稳定性、模型版本稳定性多重保证的系统工程。Claude 必须显式 cache_control 这一条都没说出来，线上多半 0% 命中率不知道。

给三条可执行的建议：

1. 今天就做一件事：打开你 LLM 调用代码，找到 response.usage，把 cache 相关字段全打到日志里，画一个命中率看板。没看板就没优化。

2. 本周做一件事：审计 system prompt 和 tool schema，把所有时间戳、session ID、user-specific 变量挪到 user message。JSON 序列化加 sort_keys=True。

3. 本月做一件事：如果是 Agent 系统，把工具集设计成固定全集，状态切换用工具调用完成。引入 <system-reminder> 模式注入动态信息。

90% 命中率不是天赋，是纪律。

一句话总结
prompt caching 真正难的不是「会用」，是「不破」。每一次部署都可能让前一个月的优化白干，直到你把它当 schema 一样守。