# Alo Agent · CF 算法陪练 AI Agent

一个基于大模型 Tool Calling 的 AI Agent：自动摸底算法水平、规划学习路径、从 Codeforces 选题、自动提交评测，并按提交次数分级给出错误反馈（只用自然语言/数学推导，不直接给代码）。

## ✨ 功能特点

- **摸底测试**：按依赖关系（如必须先会 sorting 才能学 dp）自动安排 10 个核心算法专题的实战测试，未达前置要求的专题自动跳过
- **个性化推题**：根据知识库中"已掌握 / 学习中 / 未涉及"的状态，在 Codeforces 题库里按 rating 区间筛题
- **自动提交与评测**：模拟登录 Codeforces 会话，自动提交代码并轮询获取 AC / WA / TLE / MLE / RE / CE 等结果，无需手动到网页上操作
- **分级反馈机制**：第一次提交只告知结果，逼自己先独立调试；第二次起才逐步给出错误定位与原因，且严格限制只能用自然语言和数学公式描述，禁止出现代码或伪代码
- **知识库与前置解锁**：基于 Markdown 文件实现的轻量知识库（可直接用 Obsidian 打开编辑），单题连续 3 次提交未过会被锁定，需补完前置算法的 AC 记录才能解锁重做
- **上下文压缩**：对话超长时自动摘要历史消息，控制 Token 消耗

## 🏗️ 架构说明

```
用户输入
   │
   ▼
run_agent()  主循环（手写 ReAct 风格 tool-calling loop，调用 DeepSeek Chat API）
   │
   ├─ get_problem            → 调用 Codeforces API 按算法/难度选题
   ├─ submit_and_get_result  → 模拟登录 + 提交代码 + 轮询评测结果
   ├─ analysis_code          → 转交给独立的 LangChain Sub-Agent 做错误分析
   ├─ updata_learning_path /
   │  finish_onboarding      → 写入知识库
   ▼
knowledge.py（Markdown 知识库 / 状态机）
```

主对话循环是手写实现的 Tool Calling 循环，目的是吃透 Agent Loop 的底层机制；其中错误分析这一子任务则用 LangChain 的 `create_agent` 实现，作为框架用法的实践，两种方式在项目里并存。

## 📁 项目结构

```
.
├── main.py        # 对话主循环、工具 schema 定义、System Prompt、上下文压缩
├── tool.py        # CF 选题 / 自动登录提交 / 评测轮询 / 错误分析子 Agent
├── knowledge.py   # 基于 Markdown 的知识库、算法依赖图、学习路径管理
└── vault/         # 运行后自动生成，存放用户画像、算法状态、做题记录（可用 Obsidian 打开）
```

## ⚙️ 环境准备

### 安装依赖

```bash
pip install openai python-dotenv langchain requests
```

### 配置 `.env`

```env
# DeepSeek API
DEEPSEEK_API_KEY=你的key

# Codeforces 会话所需 Cookie（从浏览器已登录的 Codeforces 中复制）
JSESSIONID=
39ce7=
70a7c28f3de=
cf_clearance=
X-User=

# 你的 Codeforces 用户名
CF_HANDLE=你的CF handle

# 如需代理访问 Codeforces（可选）
HTTP_PROXY=
HTTPS_PROXY=
```

> ⚠️ 上述 Cookie 字段名对应 Codeforces 网页登录后浏览器里的真实 Cookie，需手动从开发者工具中复制，且会过期，过期后需要重新获取。

## 🚀 运行

```bash
python main.py
```

- 多行输入后，单独一行输入 `end` 结束本次输入并发送给 Agent
- 输入 `quit` 退出程序

首次运行会自动触发摸底测试，依次测试 10 个核心算法专题，结束后生成你的算法能力画像并写入知识库。

## 🧭 使用流程

1. 启动后 Agent 按依赖顺序安排算法测试（sorting → binary search → two pointers → ... → graphs）
2. 针对每个算法依次推送 easy / medium / hard 三道题
3. 把代码贴给 Agent，它会自动提交到 Codeforces 并返回评测结果
4. 根据提交次数，Agent 给出由浅入深的反馈：结果 → 错误类型 → 具体定位与原因
5. 全部测试完成后，Agent 调用 `finish_onboarding` 写入知识库，并给出后续学习路径建议

## 🗺️ 后续计划

- [ ] 用 LangGraph / `create_agent` 重构主对话循环，替换手写 tool-calling loop，对比两种实现的可维护性
- [ ] 引入向量检索，对相似考点做语义化推题
- [ ] 支持多平台（AtCoder / 牛客）选题与提交

## 📄 License

MIT