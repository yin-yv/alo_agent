from openai import OpenAI
from dotenv import load_dotenv
from typing import Optional, Dict, Any
import os
import requests
import random
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
                "required": ["alg", "rat", "prerequisites", "leads_to"],   # 修复拼写
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
                        "description": "用户对本题的提交次数，决定反馈详细程度",
                    },
                    "source_code": {
                        "type": "string",
                        "description": "用户的源代码，用于分析错误位置",
                    }
                },
                "required": ["verdict", "attempt_count", "source_code"],
            }
        }
    }
]

ratting={
    "easy":(800,1200),
    "medium":(1200,2000),
    "hard":(2001,3800)
}

ALG_TAG_MAP = {
    "dp":             "dp",
    "动态规划":        "dp",
    "binary search":  "binary search",
    "二分":           "binary search",
    "graphs":         "graphs",
    "图论":           "graphs",
    "greedy":         "greedy",
    "贪心":           "greedy",
    "dfs":            "dfs and similar",
    "bfs":            "bfs",
    "tree":           "trees",
    "树":             "trees",
    "math":           "math",
    "数学":           "math",
    "sorting":        "sortings",
    "排序":           "sortings",
    "two pointers":   "two pointers",
    "双指针":         "two pointers",
    "prefix sum":     "data structures",
    "前缀和":         "data structures",
}

def get_tag(alg:str)->str:
    return ALG_TAG_MAP.get(alg.strip().lower,alg.strip().lower)

def _fetch_problem(tag:str,lo:int,hi:int,n:int)->list[dict]:
    try:
        res=requests.get(
            "https://codeforces.com/api/problemset.problems",
            param={"tags":tag},
            timeout=15
        ).josn()
    except Exception as e:
        return [{"error":f"网络请求失败{e}"}]
    if res.get("status")!="OK":
        return [{"error":f"{res.get('content','未知')}"}]
    pool=[
        p for p in res["result"]["problem"]
        if lo<=p.get("rating",0)<=hi
    ]
    if not pool:
        return []
    pro=random.sample(pool,min(n,len(pool)))
    return [
        {
            "name":p["name"],
            "rating":p.get("rating","?"),
            "contest_id":p["contestId"],
            "url":f"https://codeforces.com/contest/{p['contestId']}/problem/{p['index']}",
            "index":p["index"],
            "tags":p.get("tags",[])
        }
        for p in pro
    ]

def get_problem(alg:str,rat:str,leads_to:list[str],prerequisites:list[str]) ->Dict[str,Any]:
    """
    根据算法名和难度档位，返回结构化的题目集 + 学习路径。
 
    参数：
        alg           用户想学的算法（支持中文或英文）
        rat           难度档位：'easy' / 'medium' / 'hard'
        prerequisites 前置算法列表（由 Agent 根据知识库填入）
        leads_to      进阶算法列表（由 Agent 填入）
 
    返回：
        {
          "alg": ...,
          "tag": ...,           # 实际使用的 CF tag
          "difficulty": ...,    # rating 区间
          "prerequisites": ..., # 前置路径
          "leads_to": ...,      # 进阶路径
          "problems": [         # 推荐题目列表
            {
              "name": ...,
              "rating": ...,
              "contest_id": ...,
              "index": ...,
              "url": ...,
              "tags": [...],
            },
            ...
          ],
          "warning": ...        # 可选：前置不足时的提示
        }
    """
    if rat not in ratting:
        return [{"error":f"rat参数无效，应为easy/medium/hard，收到：{rat!r}"}]
    tags=get_tag(alg)
    lo,hi=ratting[rat]
    problem=_fetch_problem(tags,lo,hi,n=3)
    result:dict[str,Any]={
        "alg":alg,
        "tags":"tags",
        "difficulty":{"level":rat,"ratting":f"{lo}~{hi}"},
        "prerequisites":prerequisites,
        "leads_to":leads_to,
        "problems":problem
    }
    if prerequisites:
        result["warnning"]=(f"学习{alg}前，需要掌握{','.json(prerequisites)}")
    return result

      

def call_tools(name,msg):
    if name=="get_problem":
        return get_problem(**msg)

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
    return system+[{"role":"assitsant","content":f"对话摘要: {summary}"}]


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
    messages.append({"role":"user","content":user_input})
    if len(messages)>MAX_MESSAGES+5:
        messages=context_cpmress(messages,client)