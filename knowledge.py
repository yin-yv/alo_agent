"""
knowledge.py
基于 Obsidian Vault（纯 Markdown）的知识库模块。可直接在 Obsidian 中查看和编辑。
 
Vault 目录结构：
  vault/
    user_profile.md          # 用户画像（掌握情况总览）
    learning_path.md         # 当前学习路径
    algorithms/              # 每种算法一个文件
      dp.md
      binary-search.md
      ...
    problems/                # 每道做过的题一个文件
      1A.md
      ...
"""
import re
from datetime import date
from pathlib import Path
from typing import Optional
from langchain.tools import tool

VAULT=Path(__file__).parent/"vault"
ALG=VAULT/"algorithms"
PRO=VAULT/"problems"

MAX_ATTEMPT=3

ONBOARDING_ALGOS = [
    "sorting",        
    "binary search",  
    "two pointers",   
    "greedy",         
    "math",           
    "dfs and similar",
    "bfs",            
    "dp",             
    "trees",          
    "graphs",         
]

ALGO_DEPS: dict[str, list[str]] = {
    "sorting":        [],
    "binary search":  ["sorting"],
    "two pointers":   ["sorting"],
    "greedy":         ["sorting"],
    "math":           [],
    "dfs and similar":["sorting"],
    "bfs":            ["dfs and similar"],
    "dp":             ["sorting", "greedy"],
    "trees":          ["dfs and similar"],
    "graphs":         ["bfs", "dfs and similar"],
}

def _ensure_dirs():
    for d in (VAULT,ALG,PRO):
        d.mkdir(parents=True,exist_ok=True)

def _read_md(path:Path)->dict:
    if not path.exists():
        return {}
    text=path.read_text(encoding="utf-8")
    m=re.match(r"^---\n(.*?)\n---",text,re.DOTALL)
    if not m:
        return {}
    data={}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key,_,raw=line.partition(":")
        key=key.strip()
        raw=raw.strip()
        if raw.startswith("[") and raw.endswith("]"):
            inner=raw[1:-1]
            data[key]=[x.strip() for x in inner.split(",")] if inner else []
        elif raw.lower()=="true":
            data[key]="true"
        elif raw.lower()=="false":
            data[key]="false"
        elif raw.isdigit():
            data[key]=int(raw)
        else:
            data[key]=raw
    return data

def _write_md(path:Path,data:dict,body:str=""):
    lines=["---"]
    for k,v in data.items():
        if isinstance(v,list):
            inner=", ".join(str(x) for x in v)
            lines.append(f"{k}:[{inner}]")
        elif isinstance(v,bool):
            lines.append(f"{k}:{'true' if v else 'false'}")
        else:
            lines.append(f"{k}:{v}")
    lines.append("---")
    if body:
        lines.append("")
        lines.append(body)
    path.write_text("\n".join(lines)+"\n",encoding="utf-8")

def _alg_path(alg_tag:str)->Path:
    name=alg_tag.strip().lower().replace(" ","-")
    return ALG/f"{name}.md"

def _pro_path(contextId:int|str,index:str)->Path:
    return PRO/f"{contextId}{index.lower()}.md"

def init_vault():
    _ensure_dirs()
    profile_path=VAULT/"user_profile.md"
    if not profile_path.exists():
        _write_md(
            profile_path,{
                "onboarding_done":"false",
                "mastered":[],
                "learn":[],
                "not_started":[]
                },
            body="#用户学习档案\n\n在此记录学习过程"
            )
    lp=VAULT/"learning_path.md"
    if not lp.exists():
        _write_md(lp,{
            "current_alg":"",
            "next_alg":[]
        },body="当前的学习路径")
        
def get_user():
    return _read_md(VAULT/"user_profile.md")

def set_boarding():
    p=VAULT/"user_profile.md"
    data=_read_md(p)
    data["onboarding_done"]="True"
    _write_md(p,data)

def get_master_alg()->list[str]:
    return get_user().get("mastered",[])

def get_learn_alg()->list[str]:
    return get_user().get("learn",[])

STATUS_NOT_STARTED="not_started"
STATUS_LEARN="learn"
STATUS_MASTERED="mastered"

def get_alg_status(alg_tag:str)->dict:
    """
    读取某算法的状态。
    返回格式：
      {
        "status": "not_started" | "learning" | "mastered",
        "difficulty_reached": "easy" | "medium" | "hard" | "",
        "prerequisites": [...],
        "leads_to": [...],
        "last_practiced": "2025-06-10",
        "notes": "...",
      }
    """
    data=_read_md(_alg_path(alg_tag))
    if not data:
        return {
            "status":STATUS_NOT_STARTED,
            "difficulty_reached":"",
            "prerequisites":[],
            "leads_to":[],
            "last_practiced":"",
            "notes":""
        }
    return data

def updata_alg_status(
        alg_tag:str,
        status:Optional[str]=None,
        difficulty_reached:Optional[str]=None,
        prerequisites:Optional[str]=None,
        leads_to:Optional[str]=None,
        notes:Optional[str]=None
):
    _ensure_dirs()
    path=_alg_path(alg_tag)
    data=_read_md(path) or{
        "status":STATUS_NOT_STARTED,
        "difficulty_reached":"",
        "prerequisites":[],
        "leads_to":[],
        "last_practiced":"",
        "notes":""
    }
    if status is not None:
        data["status"]=status
    if difficulty_reached is not None:
        data["difficulty_reached"]=difficulty_reached
    if prerequisites is not None:
        data["prerequisites"]=prerequisites
    if leads_to is not None:
        data["leads_to"]=leads_to
    if notes is not None:
        data["notes"]=notes
    data["last_practiced"]=str(date.today())
    _write_md(path,data)
    _sync_profile(alg_tag,data["status"])

def _sync_profile(alg_tag:str,new_status:str):
    """
    根据算法的最新状态，更新 user_profile.md 的三个列表：
    mastered / learning / not_started。
    """
    p=VAULT/"user_profile.md"
    data=_read_md(p)
    for key in ("mastered","learn","not_started"):
        lst=data.get(key,[])
        if alg_tag in lst:
            lst.remove(alg_tag)
        data[key]=lst
    target_key={
        STATUS_MASTERED:"mastered",
        STATUS_LEARN:"learn",
        STATUS_NOT_STARTED:"not_started"
    }.get(new_status,"not_started")
    lst=data.get(target_key,[])
    if alg_tag not in lst:
        lst.append(alg_tag)
    data[target_key]=lst
    _write_md(p,data)

def get_problem_record(contest_id:int|str,index:str):
    data=_read_md(_pro_path(contest_id,index))
    if not data:
        return {
            "contestId":int(contest_id),
            "index":index,
            "alg_tag":"",
            "attempt_count":0,
            "url":"",
            "status":""
        }
    data.setdefault("unlock_count",0)
    return data

def can_submit(contest_id:int|str,index:str):
    record=get_problem_record(contest_id=contest_id,index=index)
    if record["attempt_count"]<MAX_ATTEMPT:
        return {"allowed":True}
    alg_tag=record.get("alg_tag","")
    if not alg_tag:
        return {
            "allowed":    False,
            "reason":     f"该题已达 {MAX_ATTEMPT} 次提交上限，且未绑定算法标签，无法自动解锁。",
            "unlockable": False,
        }
    alg_data=get_alg_status(alg_tag)
    prerequisites=alg_data.get("prerequisites",[])
    if not prerequisites:
        return {
            "allowed":    False,
            "reason":     f"该题已达 {MAX_ATTEMPT} 次提交上限，且 {alg_tag} 没有前置算法可巩固。",
            "unlockable": False,
        }
    unfinished=[q for q in prerequisites if not _prereq_has_ac(q)]
    if unfinished:
        return {
            "allowed":       False,
            "reason":        (
                f"该题已达 {MAX_ATTEMPT} 次提交上限。"
                f"完成以下前置算法各至少一道 AC 后可自动解锁：{', '.join(unfinished)}"
            ),
            "prerequisites": unfinished,
            "unlockable":    True,
        }
    _do_unlock(contest_id,index)
    return {"allowed":True}

def _prereq_has_ac(alg_tag)->bool:
    if not PRO.exists():
        return False
    for f in PRO.glob("*.md"):
        data=_read_md(f)
        if data.get("alg_tag")==alg_tag and data.get("status")=="AC":
            return True
    return False

def _do_unlock(contest_id:int|str,index:str):
    path=_pro_path(contest_id,index)
    data=get_problem_record(contest_id=contest_id,index=index)
    data["attempt_count"]=0
    data["unlock_count"]=data.get("unlock_count",0)+1
    history=data.get("history",[])
    history.append(f"UNLOCK_COUNT #{data['unlock_count']}")
    data["history"]=history
    _write_md(path,data)

def check():
    if not PRO.exists():
        return
    for f in PRO.glob("*.md"):
        data=_read_md(f)
        if not data:
            continue
        if data.get("attempt_count",0)<MAX_ATTEMPT:
            continue
        alg_tag=data.get("alg_tag","")
        if not alg_tag:
            continue
        alg_data=get_alg_status(alg_tag)
        prerequisites=alg_data.get("prerequisites",[])
        if not prerequisites:
            continue
        if all(_prereq_has_ac(p) for p in prerequisites):
            contestId=data.get("contest_id","")
            index=data.get("index","")
            if contestId and index:
                _do_unlock(contestId,index)

def record_submission(
        contestId:int|str,
        index:str,
        verdict:str,
        alg_tag:str="",
        url:str=""
):
    _ensure_dirs()
    path=_pro_path(contestId,index)
    data=_read_md(path) or {
        "contest_id":      str(contestId),
        "index":           index.upper(),
        "alg_tag":         alg_tag or "",
        "attempt_count":   0,
        "verdict_history": [],
        "status":          "",
        "url":             url or "",
    }
    if alg_tag:
        data["alg_tag"]=alg_tag
    if url:
        data["url"]=url
    data["attempt_count"]=data.get("attempt_count",0)+1
    history=data.get("verdict_history",[])
    history.append(verdict)
    data["verdict_history"]=history
    data["status"]=verdict
    _write_md(path,data)
    if verdict=="AC" and alg_tag:
        _on_ac(alg_tag)
        check()
    return data

def _on_ac(alg_tag:str):
    data=_read_md(_alg_path(alg_tag))
    if data:
        data["last_practiced"]=str(date.today())
        _write_md(_alg_path(alg_tag),data)

def get_attempt_count(contestId:int|str,index:str):
    return get_problem_record(contestId,index).get("attempt_count",0)

def get_learn_path():
    return _read_md(VAULT/"learning_path.md")

def updata_learning_path(current_alg:str,next_alg:list[str]):
    _write_md(VAULT/"learning_path.md",{
        "current_alg":current_alg,
        "next_alg":next_alg
    })

def check_onboarding()->str|None:
    profile=get_user()
    onboarding=profile.get("onboarding_done")
    if onboarding=="True":
        return None
    algo_list="\n".join(
        f"{i+1}.{alg}(前置：{', '.join(ALGO_DEPS[alg]) or '无'})"
        for i,alg in enumerate(ONBOARDING_ALGOS)
    )
    return f"""## 系统指令：首次使用摸底（本指令仅执行一次，执行完毕后自动失效）
 
---
 
### 一、摸底目标
 
通过让用户**实际解题**，客观探明其算法掌握程度，写入知识库，为后续学习路径提供依据。
禁止用问卷或口头询问"你会不会 XXX"来替代做题评估。
 
---
 
### 二、摸底算法清单（按依赖顺序）
 
{algo_list}
 
**跳过规则**：若某算法的所有前置算法均未被用户掌握（`not_started`），
则该算法自动跳过，标记为 `not_started`，不出题。
 
---
 
### 三、每个算法的出题与判定流程
 
#### 3.1 出题
 
对当前算法，调用 `get_problem` 按以下顺序依次推送题目：
 
| 轮次 | 难度   | rating 区间  | 目的             |
|------|--------|-------------|-----------------|
| 第1题 | easy   | ≤ 1200      | 验证基础概念     |
| 第2题 | medium | 1200–2000   | 验证熟练度       |
| 第3题 | hard   | > 2000      | 验证综合运用     |
 
- 每题只有在用户**请求下一题**或当前题已判定（AC / 耗尽提交）后才推送下一题。
- 每题最多 {MAX_ATTEMPT} 次提交机会，用尽视为未通过。
 
#### 3.2 掌握程度判定（每个算法独立判定）
 
| 通过情况                  | 判定结果      | 含义                   |
|--------------------------|--------------|------------------------|
| easy、medium、hard 全 AC  | `mastered`   | 深度掌握               |
| easy 和 medium AC         | `learn`      | 掌握主干，尚需提高     |
| 仅 easy AC                | `learn`      | 了解基础概念           |
| easy 未 AC（耗尽提交）    | `not_started`| 实质未掌握             |
 
> 注意：用户可以在任何题上主动放弃（输入"跳过"/"不会"），
> 放弃 easy 等同于 easy 未 AC，直接判定 `not_started`，跳至下一算法。
 
#### 3.3 提交反馈规则（摸底期间同样适用）
 
- **第 1 次提交**：只告知 AC / 非 AC，不透露错误原因。
- **第 2、3 次提交**：给出错误的大致位置和原因（自然语言，禁止代码）。
- 非 AC 时，鼓励用户继续思考，但不主动提示解法方向。
 
---
 
### 四、摸底进度管理
 
- 在每个算法开始前，简短告知用户当前进度，例如：
  > "现在测试第 3 项：双指针（2/10）"
- 所有算法结束后，向用户展示摸底汇总，然后**立即调用 `finish_onboarding`** 写库。
 
---
 
### 五、摸底汇总格式（调用 finish_onboarding 前展示给用户）
 
```
📊 摸底完成！以下是你的算法基础画像：
 
✅ 已掌握（mastered）：sorting、binary search
📖 学习中（learn）：greedy、math
⬜ 未涉及（not_started）：dp、graphs、trees
 
🎯 推荐从「two pointers」开始，逐步衔接 dp 路径。
```
 
---
 
### 六、调用 finish_onboarding 的时机与要求
 
- **时机**：展示汇总后立即调用，不等用户确认。
- **参数完整性**：`mastered`、`learn`、`not_started` 三个列表必须覆盖
  所有 ONBOARDING_ALGOS 中的算法（跳过的算法填入 `not_started`）。
- `current_alg`：推荐用户接下来重点学习的算法（通常是 `learn` 列表中
  依赖已满足、难度最低的一个）。
- `next_alg`：后续 2–4 个进阶算法，按建议学习顺序排列。
 
---
### 七、示例
- 专题：排序
- 题目：CF 1933A tag：贪心、数学、排序
- ...
- 专题：动态规划
- 题目：CF 2237H tag：动态规划、树
- ...
现在开始第一题
---
### 八、代码提交流程（摸底期间同样强制执行）

**触发条件**：用户粘贴代码，或明确表示"提交"、"测评"等意图。

**执行步骤**：
1. 必须调用 `submit_and_get_result` 工具，将代码提交至 Codeforces 并获取评测结果。
2. **禁止**在未调用该工具的情况下，自行判断、猜测或编造评测结果。
3. 获取结果后，按本指令第 3.3 节的反馈规则回复用户，并据此更新当前题目的判定状态（AC / 耗尽提交 / 放弃）。
---
### 九、禁止行为
 
- ❌ 禁止用口头问答（"你会 DP 吗？"）代替实际做题评估
- ❌ 禁止在 easy 未通过的情况下仍推送 medium / hard
- ❌ 禁止在摸底期间给出解题代码或伪代码
- ❌ 禁止跳过 `finish_onboarding` 调用或仅部分写库
- ❌ 禁止在摸底结束前进入正式学习模式
 
---
 
现在开始摸底，用中文与用户交流。先用一句话介绍摸底目的，然后从第一个算法出题。"""

@tool(description="完成初始化引导流程")
def finish_onboarding(mastered:list[str],learn:list[str],not_started:list[str],current_alg:str,next_alg:list[str]):
    _ensure_dirs()
    for tag in mastered:
        updata_alg_status(tag,status=STATUS_MASTERED)
    for tag in learn:
        updata_alg_status(tag,status=STATUS_LEARN)
    for tag in not_started:
        updata_alg_status(tag,status=STATUS_NOT_STARTED)
    updata_learning_path(current_alg,next_alg)
    set_boarding()
    return {
        "status":"onboarding_complete",
        "mastered":mastered,
        "learn":learn,
        "not_started":not_started,
        "current_alg":current_alg,
        "next_alg":next_alg
    }


def build_prompt()->str:
    profile=get_user()
    master=profile.get("mastered",[])
    learning=profile.get("learn",[])
    not_started=profile.get("not_started",[])
    onboarding=str(profile.get("onboarding_done",False)).lower()=="true"
    lp=get_learn_path()
    lines = ["## 用户知识库（实时）"]
    lines.append(f"- 初始化测试完成: {'是' if onboarding else '否'}")
    lines.append(f"- 已掌握算法: {', '.join(master) if master else '无'}")
    lines.append(f"- 正在学习: {', '.join(learning) if learning else '无'}")
    lines.append(f"- 尚未涉及: {', '.join(not_started) if not_started else '未记录'}")
    if lp.get("current_alg"):
        lines.append(f"- 当前学习路径: {lp['current_alg']} → {', '.join(lp.get('next_alg', []))}")
    lines.append(f"- 每题最多提交次数: {MAX_ATTEMPT}")
    return "\n".join(lines)
