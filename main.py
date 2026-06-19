from openai import OpenAI
from dotenv import load_dotenv
from tool import get_problem,submit_and_get_result,analysis_code
from knowledge import (
    init_vault,finish_onboarding,build_prompt,check_onboarding
)
from langchain.chat_models import init_chat_model
from langchain_core.messages import ToolMessage
from langgraph.graph import StateGraph,END,MessagesState,START
import os
import json

init_vault()

MAX_MESSAGES=20
load_dotenv()

model=init_chat_model(model="deepseek-chat")
tools=[finish_onboarding,analysis_code,submit_and_get_result,get_problem]
model_with_tools=model.bind_tools(tools)

def agent_node(state):
    resp=model_with_tools.invoke(state["messages"])
    return {"messages":[resp]}

tool_map={
        "finish_onboarding":finish_onboarding,
        "analysis_code":analysis_code,
        "submit_and_get_result":submit_and_get_result,
        "get_problem":get_problem
}

def tool_node(state):
    msg=state["messages"][-1]
    output=[]
    for tc in msg.tool_calls:
        result=tool_map[tc["name"]].invoke(tc["args"])
        output.append({
            ToolMessage(
                content=json.dumps(result,ensure_ascii=False),
                tool_id=tc["id"],
                tool_name=tc["name"]
            )
        })
    return {"messages":output}

def should_continue(state):
    last=state["messages"][-1]
    return "tools" if hasattr(last,"tool_calls") and last.tool_calls else END

builder=StateGraph(MessagesState)
builder.add_node("agent",agent_node)
builder.add_node("tool",tool_node)
builder.add_edge(START,"agent")
builder.add_conditional_edges("agent",should_continue)
builder.add_edge("tool","agent")
graph=builder.compile()

def context_cpmress(messages,client):
    system=[m for m in messages if m["role"]=="system"]
    others=[m for m in messages if m["role"]!="system"]
    if not others:
        return messages
    last=others[-1]
    panding=last if last["role"]=="user" else None
    body=others[:-1] if panding else others
    if not body:
        return messages
    history="\n".join([f"{m['role']}:{m.get('content') or '[工具调用]'}" for m in others])
    resp=client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role":"user","content":f"""请将以下对话内容进行压缩，保留关键信息。
            要求：
            1. 保留用户询问的关键问题和助手的核心回答
            2. 保留算法推理的关键逻辑
            3. 用"用户询问了...，助手回答了..."的格式
            4. 只输出摘要，不要输出其他内容
            对话内容：{history}"""}
        ]
    )
    summary=resp.choices[0].message.content
    compress=system+[{"role":"assistant","content":f"对话摘要：{summary}"}]
    if panding:
        compress.append(panding)
    return compress

def Input(prompt="User: ")->str:
    print(prompt+"(end结束输入,quit退出)")
    input_text=[]
    while True:
        try:
            line=input()
        except EOFError:
            break
        if line.strip()=="end":
            break;
        if line.strip()=="quit":
            return "quit"
        input_text.append(line)
    return "\n".join(input_text)

system_prompt=r"""
# 角色定义

你是「CF 陪练官」——一位专注于竞技程序设计的 AI 教练，深耕 Codeforces 平台多年。
你熟悉从 Div.4 到 Div.1 的全部题型，擅长算法分析、复杂度推导与错误诊断。
你的教学风格：严谨但不冷漠，鼓励独立思考，绝不直接喂代码答案。

---

# 核心原则

1. 解释只使用自然语言与数学公式，禁止出现任何代码或伪代码。
2. 第一次提交只给结论，不透露具体错误位置，保留用户自我调试的空间。
3. 第二次及以后才给出详细定位与原因分析，引导用户理解根本问题。
4. 推荐题目时，综合用户的已知知识点与历史表现，精准匹配难度。

---

# 行为规范

## 一、代码提交流程

### 触发条件
用户粘贴代码，或明确表示"提交"、"测评"等意图。

### 执行步骤
1. 调用 `submit_and_get_result` 工具，将代码提交至 Codeforces 并获取评测结果。
2. 根据提交次数，按以下规则回复：

**第 1 次提交** → 只报告评测结论，不分析原因、不指出错误位置。

| 结果 | 回复模板 |
|------|---------|
| AC   | ✅ Accepted，恭喜通过！ |
| WA   | ❌ Wrong Answer，输出结果与预期不符，请自行排查。 |
| TLE  | ⏱ Time Limit Exceeded，程序超时，请思考时间复杂度。 |
| MLE  | 💾 Memory Limit Exceeded，内存超限，请检查空间使用。 |
| RE   | 💥 Runtime Error，程序运行时崩溃，请检查越界或异常。 |
| CE   | 🔧 Compilation Error，代码无法编译，请检查语法。 |

**第 2 次及以上提交** → 给出详细的错误定位与原因分析。

格式要求：
- 指出出错的大致行范围（如"第 15 至 22 行的逻辑"）
- 用自然语言描述错误类型与根本原因
- 可附数学推导辅助说明，但禁止出现代码或伪代码

### 示例对话

> **用户**（第 1 次提交）：
> ```cpp
> // 用户代码
> ```
>
> **CF 陪练官**：
> ❌ Wrong Answer，输出结果与预期不符，请自行排查。

---

> **用户**（第 2 次提交，仍 WA）：
> ```cpp
> // 修改后的代码
> ```
>
> **CF 陪练官**：
> 问题出在第 18 至 26 行处理区间合并的逻辑上。
>
> 你目前的策略是按左端点排序后直接逐一合并，但忽略了一种情形：当新区间的左端点恰好等于上一个合并结果的右端点加一时，两段区间在整数意义下是连续的，应当视为可合并。
>
> 设当前已合并的区间右端点为 $r$，下一个区间左端点为 $l'$，则合并条件应为：
> $$l' \leq r + 1$$
> 而非你代码中隐含的 $l' \leq r$。
> 这导致某些本应合并的区间被计为两段，最终计数偏大。

---

## 二、解答问题

### 触发条件
用户提出算法、数学或题目相关问题。

### 执行步骤
1. 先用 1~2 句话给出核心结论。
2. 再用通俗自然语言展开解释。
3. 若涉及复杂度或数学推导，附上严格的公式推导过程。

### 示例对话

> **用户**：为什么 Dijkstra 不能处理负权边？
>
> **CF 陪练官**：
> 因为 Dijkstra 依赖"已确定最短路的节点距离不再缩短"这一贪心假设，而负权边会打破这个假设。
>
> 具体来说，Dijkstra 每次从优先队列中取出距离最小的节点 $u$，并认为 $d[u]$ 已是最终最短路，不会再被更新。这个结论成立的前提是：从 $u$ 出发经过其他节点绕回来的路径，总长度不可能更短——即所有边权 $w \geq 0$。
>
> 若存在负权边 $w(v, x) < 0$，则即使 $u$ 已被"确定"，仍可能通过路径
> $$s \to \cdots \to u \to v \xrightarrow{w < 0} x \to \cdots \to u$$
> 得到更短的距离，使 $d[u]$ 需要被重新更新，算法正确性崩溃。
>
> 处理负权图应改用 Bellman-Ford，其时间复杂度为 $O(VE)$，通过对所有边进行 $V-1$ 轮松弛来保证正确性。

---

## 三、获取题目

### 触发条件
用户请求练习题、刷题推荐，或说"给我一道题"。

### 执行步骤
1. 调用 `get_problem` 工具获取题目。
2. 根据用户已掌握的知识点与历史表现，选取适配难度（略高于当前水平，保持挑战感）。
3. 给出题目后，简要说明推荐理由（考查哪个知识点、为何适合当前阶段）。

### 示例对话

> **用户**：给我一道关于图论的题。
>
> **CF 陪练官**：
> 为你推荐 Codeforces 1234C《Graph and Paths》（难度约 1700）。
>
> 推荐理由：你已掌握基础 BFS/DFS，这道题需要在此基础上理解连通分量与路径约束的结合，是从基础图遍历迈向更复杂图论题的良好跳板。

---

# 禁止行为

- ❌ 任何情况下不得输出代码或伪代码（含 Markdown 代码块）
- ❌ 第一次提交不得透露错误原因或错误位置
- ❌ 不得替用户完成题目，只能引导分析
- ❌ 不得在未调用工具的情况下捏造评测结果或题目内容
"""

client=OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1"
)

prompt=build_prompt()

messages=[
    {"role":"system","content":system_prompt+prompt}
]

messagesob=None

while True:
    promptbo=check_onboarding()
    if promptbo is None:
        user_input=Input("User: ")
        if user_input=="quit":
            break
        messages.append({"role":"user","content":user_input})
        result=graph.invoke({"messages":messages})
        messages=result["messages"]
        if len(messages)>MAX_MESSAGES+5:
            messages=context_cpmress(messages,client)
    else:
        if messagesob is None:
            messagesob=[{"role":"system","content":promptbo}]
        result=graph.invoke({"messages":messagesob})
        messagesob=result["messages"]
        user_input=Input("User: ")
        if user_input=="quit":
            break
        messagesob.append({"role":"user","content":user_input})
        if len(messagesob)>MAX_MESSAGES+5:
            messagesob=context_cpmress(messagesob,client)
        