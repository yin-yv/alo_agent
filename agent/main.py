from openai import OpenAI
from dotenv import load_dotenv
import os

MAX_MESSAGES=20
load_dotenv()

tools=[
    {
        "type":"function",
        "function":{
            "name":"get_problem",
            "description":"根据user现有的知识库和要学习的算法，提供最适合的学习题目集",
            "parameters":{
                "type":"object",
                "properties":{
                    "rank":{
                        "type":"string"
                    },
                    "prerequisites":{
                        "type":"string",
                        "description":"获取用户是否具备学习这个算法的条件，不具有则给出前置算法"
                    },
                    "leads_to":{
                        "type":"string",
                        "description":"用户学会了这个算法后，能够学进阶的算法"
                    }
                },
                "requried":["rank","preerquisites","leads_to"]
            }
        },
        "function":{
            "name":"submit&get_result",
            "description":"用户提交代码并拿到结果,如:AC,WA,TLM",
            "parameters":{
                "type":"tool",
                "properties":{
                    "submit":{
                        "type":"string",
                        "description":"提交用户代码"
                    },
                    "result":{
                        "type":"string",
                        "description":"获取用户的提交结果"
                    },
                },
                "requried":["submit","result"]
            }
        },
        "function":{
            "name":"analysis_code",
            "description":"根据submit&get_result的返回结果，详细分析错误的原因",
            "parameters":{
                "type":"tool",
                "properties":{
                    "location":{
                        "type":"string",
                        "description":"出错的位置"
                    },
                    "incorrect_form":{
                        "type":"string",
                        "description":"因为什么出错，是语法还是逻辑"
                    }
                },
                "requried":["location","incorrect_form"]
            }
        }
    }
]

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