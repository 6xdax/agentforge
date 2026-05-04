# 可靠的 Tool Calling：三层防护实践

> 原文：[大模型工具调用可靠性的三个层次](https://mp.weixin.qq.com/s/vM0kwpptGSthpJy1PVXkaA)

## 问题：为什么 prompt 约束不够？

很多人在 prompt 里写"不许乱编参数"，测试几个例子发现没问题，一上线就崩。模型的常见瞎编行为：

- 用户问"后天天气"，直接回复"北京后天晴，15~25℃"而不调用工具
- 调用时传参 `date="后天"`（工具根本不支持这个格式）
- 自作主张把"后天"转成具体日期 `2026-04-29`（即使工具没要求这么做）

### 根本原因

LLM 的输出本质是**概率采样**，prompt 只是"软推"而非"硬锁"。模型出错时往往表现得非常自信，不会说"我不确定"，而是直接给出一个看起来合理的假参数。这不是某一家模型的缺陷，而是当前 LLM 范式的系统性特征。

## 三层解决方案

### 第一层：优化软约束（Prompt）

提示词应该像一份**操作合同**，不仅说明工具"用来干什么"，还要清楚标注每个参数的类型、边界、非法值举例。

```python
# ❌ 模糊的提示词
"city参数是城市名称"

# ✅ 清晰的提示词
"""
city参数必须是标准英文城市名，如 'Beijing'、'Shanghai'。
禁止传入：
- 自然语言短语，如 '我所在的城市'
- 中文城市名，如 '北京'
- 空字符串
"""
```

同时加入 **Few-shot 示例**，直接给模型看"正确的用户输入 → 正确的工具调用"对照组：

```python
messages = [
    {"role": "user", "content": "上海明天天气？"},
    {"role": "assistant", "content": "", "tool_calls": [
        {"id": "call_1", "name": "get_weather",
         "arguments": {"city": "Shanghai", "date": "2026-04-30"}}
    ]},
]
```

### 第二层：硬约束（JSON Schema）

不再用自然语言描述参数，而是用机器能验证的结构来定义。

```json
{
  "type": "object",
  "properties": {
    "city": {
      "type": "string",
      "description": "标准英文城市名，如 Beijing, Shanghai"
    },
    "date": {
      "type": "string",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
      "description": "日期格式 YYYY-MM-DD，仅支持今天或明天"
    },
    "unit": {
      "type": "string",
      "enum": ["celsius", "fahrenheit"]
    }
  },
  "required": ["city", "date"],
  "additionalProperties": false
}
```

**关键**：`additionalProperties: false` 至关重要——没有它，模型可以附带一个它"觉得有用"的额外字段（如 `"note": "用户没说清楚，我猜是摄氏度"`），下游系统完全不知道该怎么处理。

主流模型平台（OpenAI、Anthropic、Google）都支持在 API 层面直接传入 JSON Schema，某些平台在模型解码阶段就会做格式约束（结构化输出 / Constrained Decoding），从生成源头避免格式违规。

### 第三层：兜底机制（校验-清洗-重试闭环）

即便有 Schema，极端情况仍可能发生：模型输出了语法合规但语义荒谬的参数，或上游处理破坏了格式。

```python
def call_with_validation(model_output, schema, max_retries=3):
    for attempt in range(max_retries):
        # 1. 语法校验
        try:
            parsed = json.loads(model_output)
        except json.JSONDecodeError:
            # 尝试清洗 Markdown 标记、非法引号等
            parsed = json.loads(clean_markdown(model_output))
        
        # 2. Schema 验证
        try:
            jsonschema.validate(parsed, schema)
            return parsed  # 通过验证
        except jsonschema.ValidationError as e:
            error_msg = str(e)
        
        # 3. 清洗后仍不合规，则重试，并在新提示中指出问题
        model_output = retry_with_feedback(
            original_output=model_output,
            error=error_msg,
        )
    
    # 超过重试上限，走降级或人工兜底
    return fallback_response()
```

**注意**：重试次数必须有上限，否则死循环的重试链会造成比原始错误更大的破坏。

## 架构层面：让模型只做它该做的事

上面三层措施组合在一起，还需要一个架构层面的清醒认识：**LLM 只应当承担"决策"职能，而不应当承担"执行"职能**。

```
┌─────────────────────────────────────────────────────┐
│  模型层（决策大脑）                                   │
│  - 接收用户意图                                       │
│  - 判断调用哪个工具                                    │
│  - 生成参数                                           │
└──────────────────────┬──────────────────────────────┘
                       │ 决策（tool_call）
                       ▼
┌─────────────────────────────────────────────────────┐
│  框架层（执行骨架）                                    │
│  - Schema 校验                                       │
│  - 调用实际工具                                       │
│  - 处理重试逻辑                                       │
│  - 整合结果                                           │
└──────────────────────┬──────────────────────────────┘
                       │ 执行结果
                       ▼
┌─────────────────────────────────────────────────────┐
│  工具层（业务能力）                                    │
│  - get_weather / search 等具体实现                   │
│  - 与模型完全解耦                                     │
└─────────────────────────────────────────────────────┘
```

这种设计的好处：
- 模型出错时不会直接影响工具调用的安全性（框架层拦截）
- 工具逻辑变更不需要重新调整模型提示词（Schema 定义了接口契约）

## 下一前沿：语义层面的验证

以上所有方案在处理"参数格式"问题上效果良好，但对"参数语义"问题的覆盖仍然有限。Schema 可以告诉模型 `city` 必须是字符串，却无法告诉它"上海"和"沪"在业务上等价。

工具调用可靠性的下一个前沿是语义层面的验证——如用实体链接、知识图谱补全或领域特定的参数规范化模块来处理这类问题。

---

**总结**：控制模型调用工具的问题，不是一个"优化 prompt"的问题，而是一个**软件工程问题**。认清这一点，才算真正迈过了 LLM 应用开发的第一道门槛。
