from openai import OpenAI
from dotenv import load_dotenv
from typing import Optional, Dict, Any
from langchain.agents import create_agent
from langchain.messages import SystemMessage,HumanMessage,AIMessage
import os
import requests
import random
import re
import time
import json



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
    "ACCEPTED":                   "AC",
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
        if attempt_count>3:
            messages="""
                        同一个题错误超过三次，中止用户提交代码，认为用户前置知识不牢，巩固前置知识。"""
            
        else:
            test_case_debug=f"出错测试点：第{test_case}个\n" if test_case else ""
            messages="""你是一位算法竞赛教练。
                        只能用自然语言和数学推导分析错误，严禁出现任何代码或伪代码。
                        """
            hmessage=f"""题目考点：{tag}\n
                        评测结果：{ver}\n
                        {test_case_debug}\n
                        本题同类错误提交次数：{attempt_count}\n
                        用户源码：\n{source_code}\n
                        要求：\n
                        - 第一次提交（attempt_count==1）：只告知错误类型，不指出具体出错点\n
                        - 第二次及以上：给出详细的错误位置和原因分析\n
                        - 若与上次错误类型不同，先给予鼓励再分析新错误"""
            agent=create_agent(
                model="deepseek-v4-pro",
                system_prompt=SystemMessage(messages)
            )
            resp=agent.invoke({"messages":[HumanMessage(hmessage)]})
            return resp.content