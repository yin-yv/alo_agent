from openai import OpenAI
from dotenv import load_dotenv
from typing import Optional, Dict, Any
from langchain.agents import create_agent
from langchain.messages import SystemMessage,HumanMessage,AIMessage
from tool import get_problem,submit_and_get_result,analysis_code
import os
import requests
import random
import re
import time
import json

MAX_MESSAGES=20
load_dotenv()

tools=[
    {
        "type": "function",
        "function": {
            "name": "get_problem",
            "description": (
                "根据用户知识库和目标算法，从 Codeforces 选出最合适的题目集。"
                "返回易/中/难各一道题，以及前置和进阶算法路径。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "alg": {
                        "type": "string",
                        "description": "用户想学习的算法，需与 Codeforces tag 一致，如 'dp' 'binary search' 'graphs'",
                    },
                    "rat": {
                        "type": "string",
                        "enum": ["easy", "medium", "hard"],
                        "description": "难度档位：easy(≤1200) / medium(1200-2000) / hard(>2000)",
                    },
                    "prerequisites": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "学习本算法所需的前置算法列表，如 ['sorting', 'recursion']。不具备时返回学习路径提示。",
                    },
                    "leads_to": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "掌握本算法后可进阶的算法列表，如 ['tree dp', 'bitmask dp']",
                    }
                },
                "required": ["alg", "rat", "prerequisites", "leads_to"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_and_get_result",
            "description": (
                "将用户代码提交到 Codeforces 并等待返回评测结果。"
                "结果包括：AC / WA / TLE / MLE / RE / CE，以及出错的测试点编号。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "contest_id": {
                        "type": "integer",
                        "description": "题目所在 contest 的 ID，如题目 1A 的 contest_id 为 1",
                    },
                    "problem_index": {
                        "type": "string",
                        "description": "题目编号，如 'A' 'B' 'C1'",
                    },
                    "lang": {
                        "type": "string",
                        "enum": ["python", "pypy", "cpp17", "cpp20", "java", "c"],
                        "description": "提交语言",
                    },
                    "source_code": {
                        "type": "string",
                        "description": "用户提交的完整源代码",
                    }
                },
                "required": ["contest_id", "problem_index", "lang", "source_code"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analysis_code",
            "description": (
                "根据 submit_and_get_result 的结果，分析代码错误原因。"
                "第一次提交只给 verdict，第二次及以上给出具体位置和原因。"
                "只能用自然语言和数学推导，不得出现代码或伪代码。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "verdict": {
                        "type": "string",
                        "enum": ["WA", "TLE", "MLE", "RE", "CE"],
                        "description": "评测结果类型",
                    },
                    "test_case": {
                        "type": "integer",
                        "description": "出错的测试点编号",
                    },
                    "attempt_count": {
                        "type": "integer",
                        "description": "用户对本题的提交次数和错误类型，决定反馈详细程度",
                    },
                    "source_code": {
                        "type": "string",
                        "description": "用户的源代码，用于分析错误位置"
                    },
                    "tags":{
                        "type":"string",
                        "description":"当前题目的标签"
                    }
                },
                "required": ["verdict", "attempt_count", "source_code","tags"],
            }
        }
    }
]

def call_tools(name,msg):
    if name=="get_problem":
        return get_problem(**msg)
    if name=="submit_and_get_result":
        return submit_and_get_result(**msg)
    if name=="analysis_code":
        return analysis_code(**msg)

def run_agent(message,client):
    while True:
        resp=client.chat.completions.create(
            model="deepseek-chat",
            messages=message,
            tools=tools,
            tool_choice="auto"
        )
        msg=resp.choices[0].message
        if resp.choices[0].finish_reason=="stop":
            print(f"Assistant: {msg.content}")
            break
        elif resp.choices[0].finish_reason=="tool_calls":
            msg_dict={
                "role":msg.role,
                "content":msg.content,
                "tool_calls":[
                    {
                        "id":tc.id,
                        "type":tc.type,
                        "function":{
                            "name":tc.function.name,
                            "arguments":tc.function.arguments
                        }
                    }
                    for tc in msg.tool_calls
                ]
            }
            message.append(msg_dict)
            for tool_call in msg.tool_calls:
                tool_name=tool_call.function.name
                tool_content=json.loads(tool_call.function.arguments)
                result=call_tools(tool_name,tool_content)
                message.append(
                    {
                        "role":"tool",
                        "name":tool_name,
                        "tool_call_id":tool_call.id,
                        "content":json.dumps(result)
                    }
                )
            
def context_cpmress(messages,client):
    system=[m for m in messages if m["role"]=="system"]
    others=[m for m in messages if m["role"]!="system"]
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
    return system+[{"role":"assistant","content":f"对话摘要: {summary}"}]

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

system_prompt="""当用户提交代码时：
- 调用 submit&get_result 工具提交到 Codeforces 拿到一手评测结果
- 第一次提交：只告知 AC/WA/TLE/MLE/RE/CE，不指出具体出错点
- 第二次及以上：给出详细的错误位置和原因分析
- 解释只能用自然语言和数学推导，不得出现任何代码或伪代码
 
当用户提出问题时：
- 提供清晰准确的解答
- 用通俗语言解释复杂概念
- 回复格式：自然语言解释 + 数学公式推导
 
当用户需要题目时：
- 调用 get_problem 工具获取合适题目
- 根据用户已有知识储备推荐难度
"""

client=OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1"
)

messages=[
    {"role":"system","content":system_prompt}
]

while True:
    user_input=Input("User: ")
    if user_input=="quit":
        break
    messages.append({"role":"user","content":user_input})
    run_agent(messages,client)
    if len(messages)>MAX_MESSAGES+5:
        messages=context_cpmress(messages,client)