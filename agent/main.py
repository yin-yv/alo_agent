from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

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

system_prompt="""你是一个严谨竞赛算法教练。
当用户提交代码时，你会先分析代码的功能和逻辑，指出其中的错误和不足之处，并给出详细的改进建议。
当用户提出问题时，你会根据问题的内容，提供清晰准确的解答，并给出相关的示例和参考资料。
请你在回答时，保持专业和耐心，尽量用通俗易懂的语言来解释复杂的概念和算法。
回复格式：自然语言解释+数学公式推导。不得出现任何代码和伪代码"""

client=OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1"
)

messages=[
    {"role":"system","content":system_prompt}
]
while True:
    user_input=Input("User: ")