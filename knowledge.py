"""
knowledge_base.py
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

VAULT=Path(__file__).parent/"vault"
ALG=VAULT/"algorithms"
PRO=VAULT/"problems"

MAX_ATTEMPT=3

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
    name=alg_tag.strip().lower().replace("","-")
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
    if lp.exists():
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
            "status":"",
            "record_history":[]
        }
    data.setdefault("unlock_count",0)
    return data

def can_submit(contest_id:int|str,index:str):
    record=get_problem_record(contest_id=contest_id,index=index)
    if record["attempt_count"]<MAX_ATTEMPT:
        return {"allowed":True}
    alg_tag=record.get("alg_tag","")
    if alg_tag is None:
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

def check(completed_tag:str):
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
        check(alg_tag)
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

def build_prompt()->str:
    profile=get_user()
    master=profile.get("mastered",[])
    learning=profile.get("learn",[])
    not_started=profile.get("not_started",[])
    onboarding=profile.get("onboarding_done",False)
    lp=get_learn_path()
    lines = ["## 用户知识库（实时）"]
    lines.append(f"- 初始化测试完成: {'是' if onboarding else '否'}")
    lines.append(f"- 已掌握算法: {', '.join(master) if master else '无'}")
    lines.append(f"- 正在学习: {', '.join(learning) if learning else '无'}")
    lines.append(f"- 尚未涉及: {', '.join(not_started) if not_started else '未记录'}")
    if lp.get("current_alg"):
        lines.append(f"- 当前学习路径: {lp['current_alg']} → {', '.join(lp.get('next_algs', []))}")
    lines.append(f"- 每题最多提交次数: {MAX_ATTEMPT}")
    return "\n".join(lines)
