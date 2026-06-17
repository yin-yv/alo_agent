from openai import OpenAI
from dotenv import load_dotenv
from typing import Optional, Dict, Any
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

rating={
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

_LANG_ID: Dict[str, str] = {
    "python":  "7",   # Python 3
    "pypy":    "41",  # PyPy 3
    "cpp17":   "54",  # GNU G++17
    "cpp20":   "73",  # GNU G++20
    "java":    "36",  # Java 11
    "c":       "43",  # GNU GCC C11
}

_VERDICT_MAP: Dict[str, str] = {
    "OK":                        "AC",
    "Accpect":                   "AC",
    "WRONG_ANSWER":              "WA",
    "TIME_LIMIT_EXCEEDED":       "TLE",
    "MEMORY_LIMIT_EXCEEDED":     "MLE",
    "RUNTIME_ERROR":             "RE",
    "COMPILATION_ERROR":         "CE",
    "IDLENESS_LIMIT_EXCEEDED":   "ILE",
    "SKIPPED":                   "SK",
    "CRASHED":                   "CRASH",
    "REJECTED":                  "REJ",
}

_PENDING = {"TESTING", "IN_QUEUE"}

def get_tag(alg:str)->str:
    return ALG_TAG_MAP.get(alg.strip().lower(),alg.strip().lower())

def _fetch_problem(tag:str,lo:int,hi:int,n:int)->list[dict]:
    try:
        proxies={
            "HTTP_PROXY":os.getenv("HTTP_PROXY"),
            "HTTPS_PROXY":os.getenv("HTTPS_PROXY")
        }
        res=requests.get(
            "https://codeforces.com/api/problemset.problems",
            params={"tags":tag},
            proxies=proxies,
            timeout=15
        ).json()
    except Exception as e:
        return [{"error":f"网络请求失败{e}"}]
    if res.get("status")!="OK":
        return [{"error":f"{res.get('content','未知')}"}]
    pool=[
        p for p in res["result"]["problems"]
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
    if rat not in rating:
        return [{"error":f"rat参数无效，应为easy/medium/hard，收到：{rat!r}"}]
    tags=get_tag(alg)
    lo,hi=rating[rat]
    problem=_fetch_problem(tags,lo,hi,n=3)
    result:dict[str,Any]={
        "alg":alg,
        "tags":tags,
        "difficulty":{"level":rat,"ratting":f"{lo}~{hi}"},
        "prerequisites":prerequisites,
        "leads_to":leads_to,
        "problems":problem
    }
    if prerequisites:
        result["warning"]=(f"学习{alg}前，需要掌握{', '.join(prerequisites)}")
    return result

def _poll():
    for _ in range(3):
        yield 5
    for _ in range(3):
        yield 10
    while True:
        yield 20

def get_cookie()->requests.Session:
    #"从.env获取cookie"
    cookie_file=["JSESSIONID","39ce7","70a7c28f3de","cf_clearance","X-User"]
    cookie={f:os.getenv(f,"") for f in cookie_file}
    missing=[k for k,v in cookie.items() if not v]
    if missing:
        raise EnvironmentError(f"缺少关键字段:{', '.join(missing)}")
    s=requests.Session()
    s.headers.update(
        {
            "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://codeforces.com/"
        }
    )
    s.proxies={
        "http":os.getenv("HTTP_PROXY",""),
        "https":os.getenv("HTTPS_PROXY","")
    }
    for k,v in cookie.items():
        s.cookies.set(k,v,domain=".codeforces.com")
    return s

def get_crsf(session:requests.Session,url:str)->str:
    resp=session.get(url,timeout=15)
    resp.raise_for_status()
    m=re.search(r'<meta\s+name="X-Csrf-Token"\s+content="([^"]+)"',resp.text)
    if not m:
        raise ValueError("无法获取crsf，请检查cookie是否有效")
    return m.group(1)

def _is_contest_running(session, contest_id) -> bool:
    try:
        resp = session.get(
            "https://codeforces.com/api/contest.list",
            params={"gym": False},
            timeout=10
        )
        data = resp.json()
        if data.get("status") != "OK":
            return False
        for c in data["result"]:
            if c["id"] == int(contest_id):
                return c.get("phase") == "CODING"
        return False
    except Exception:
        return False

def _submit(session:requests.Session,source_code:str,contest_id:int,problem_index:str,lang:str)->None:
    if contest_id >= 100000:
        submit_url = f"https://codeforces.com/gym/{contest_id}/submit"
        index_field = "submittedProblemIndex"
    else:
        if _is_contest_running(session, contest_id):
            submit_url = f"https://codeforces.com/contest/{contest_id}/submit"
            index_field = "submitProblemIndex"
        else:
            submit_url = "https://codeforces.com/problemset/submit"
            index_field = "submittedProblemIndex"
    csrf=get_crsf(session,submit_url)
    lang_id=_LANG_ID.get(lang)
    if lang_id is None:
        raise ValueError(f"不支持当前语言，可选{list(_LANG_ID)}")
    pal={
        "csrf_token":csrf,
        "programTypeId":lang_id,
        "source":source_code,
        "contestId":str(contest_id),
        "action":"submitSolutionFormSubmit",
        "tabSize":"4",
        index_field:problem_index.upper(),
        "_tta": str(int(time.time() * 1000) % 1000)
    }
    resp=session.post(
        submit_url,
        data=pal,
        params={"csrf_token":csrf},
        timeout=20,
        allow_redirects=True
    )
    resp.raise_for_status()
    if "submitSolutionFormSubmit" in resp.url or resp.status_code !=200:
        err_m=re.search(r'error[^>]*>([^<]{5,200})', resp.text, re.I)
        hint=err_m.group(1).strip() if err_m else "位置错误，请确认cookie未到期"
        raise RuntimeError(f"CF提交失败：{hint}")
    if resp.url.endswith(f"/contest/{contest_id}/submit"):
        raise RuntimeError("CF提交失败：页面未正常跳转，cookie可能已失效")
    print(f"  [DEBUG] 提交后跳转到: {resp.url}, 状态码: {resp.status_code}")

def _least_submissionId(session:requests.Session,contest_id:int,problem_id:str)->int:
    handle = os.getenv("CF_HANDLE", "")
    if not handle:
        raise EnvironmentError("无法获取CF用户handle，请在.env中设置CF_HANDLE=你的用户名")
    url="https://codeforces.com/api/contest.status"
    resp=session.get(
        url,
        params={"contestId":contest_id,"handle":handle,"from":1,"count":50},
        timeout=15
    )
    resp.raise_for_status()
    data=resp.json()
    if data.get("status") !="OK":
        raise RuntimeError(f"获取列表失败，{data.get('comment','未知')}")
    target_Index=problem_id.upper()
    for sub in data["result"]:
        if sub.get("problem",{}).get("index","").upper()==target_Index:
            return sub["id"]
    raise RuntimeError(
        f"未找到 context {contest_id} 题目 {problem_id} 的提交记录，"
        "可能提交尚未入库，请稍后重试"
    )
#轮询结果
def _poll_verdict(session:requests.Session,submission_id:int,contest_id:str,timeout=120)->dict[str,Any]:
    url="https://codeforces.com/api/contest.status"
    deadline=timeout+time.time()
    intervals=_poll()
    handle = os.getenv("CF_HANDLE", "")
    if not handle:
        raise EnvironmentError("无法获取CF用户handle，请在.env中设置CF_HANDLE=你的用户名")
    while time.time()<deadline:
        try:
            resp=session.get(
                url,
                params={"contestId":contest_id,"handle":handle,"from":1,"count":50},
                timeout=15
            )
            resp.raise_for_status()
            data=resp.json()
        except Exception as e:
            raise RuntimeError(f"轮询结果时网络异常{e}")
        if data.get("status") !="OK":
            raise RuntimeError(f"API返回错误：{data.get('comment','未知')}")
        for sub in data["result"]:
            if sub["id"]!=submission_id:
                continue
            raw_verdict=sub.get("verdict","TESTING")
            if raw_verdict in _PENDING:
                print(f"  ⏳ 评测中（{raw_verdict}）… submission #{submission_id}")
                break
            verdict=_VERDICT_MAP.get(raw_verdict,raw_verdict)
            test_case=sub.get("passedTestCount")
            failed_case=(test_case+1) if verdict !="AC" and test_case is not None else None
            return {
                "verdict":verdict,
                "contest_id":contest_id,
                "submissionId":submission_id,
                "test_case":failed_case
            }
        else:
            print(f"  ⏳ 等待 submission #{submission_id} 出现在评测队列…")
            sleep=next(intervals)
            time.sleep(min(sleep,deadline-time.time()))
    raise TimeoutError(
        f"评测超时（>{timeout}s），submission #{submission_id} 尚未返回结果。\n"
        "可能原因：网络波动 / CF 服务器繁忙 / cookie 已失效。\n"
        "建议：检查网络后告知我重试，无需在 CF 上重复提交。"
    )

def submit_and_get_result(contest_id:str,problem_index:str,lang:str,source_code:str)->str:
    session=get_cookie()
    #提交
    print(f"  📤 正在提交 contest {contest_id} / {problem_index.upper()} ({lang})…")
    _submit(session,source_code,contest_id,problem_index,lang)
    #获取submission_id
    submission=None
    for _ in range(6):
        time.sleep(5)
        try:
            submission = _least_submissionId(session, contest_id, problem_index)
            print(f"  ✅ 提交成功，submission ID = {submission}（无需在 CF 上重复提交）")
            break
        except RuntimeError:
            print(f"  ⏳ 等待提交入库… ({_+1}/6)")
    if submission==None:
        raise RuntimeError("提交入库超时，请稍后手动查询结果")
    #轮询结果
    result=_poll_verdict(session,submission,contest_id,timeout=120)
    verdict_list=(
        f"  🏁 评测完成：{result['verdict']}"
        + (f"(在第{result['test_case']}个测试点出错)" if result['test_case'] else "")
    )
    print(verdict_list)
    return result

def analysis_code(verdict:str,attempt_count:int,source_code:str,tags:str,test_case:int=None)->str:
    ver=_VERDICT_MAP.get(verdict,verdict)
    tag=get_tag(tags)
    if ver=="AC":
        return "厉害，通过啦！"
    else:
        test_case_debug=f"出错测试点：第{test_case}个\n" if test_case else ""
        resp=client.chat.completions.create(
            model="deepseek-chat",
            messages=[ 
                {
                    "role":"system","content":(
                    "你是一位算法竞赛教练。"
                    "只能用自然语言和数学推导分析错误，严禁出现任何代码或伪代码。"
                    )
                },
                {
                    "role":"user","content":(
                        f"题目考点：{tag}\n"
                        f"评测结果：{ver}\n"
                        f"{test_case_debug}\n"
                        f"本题同类错误提交次数：{attempt_count}\n"
                        f"用户源码：\n{source_code}\n"
                        f"要求：\n"
                        f"- 第一次提交（attempt_count==1）：只告知错误类型，不指出具体出错点\n"
                        f"- 第二次及以上：给出详细的错误位置和原因分析\n"
                        f"- 若与上次错误类型不同，先给予鼓励再分析新错误"
                    )
                }
            ]
        )
        msg=resp.choices[0].message.content
        return msg

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