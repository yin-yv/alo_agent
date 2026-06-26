"""
app.py ── alo_agent Gradio 前端
用法：python app.py
依赖：pip install gradio
"""

import os
import threading
import queue
import gradio as gr
from dotenv import load_dotenv, set_key
from pathlib import Path
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage

# ── 加载环境变量 ──────────────────────────────────────────────
load_dotenv()
ENV_PATH = Path(".env")

# ── 延迟导入 agent（需要 .env 已存在） ────────────────────────
_agent_ready = False
graph = None
build_prompt = None
check_onboarding = None
system_prompt = None

REQUIRED_COOKIES = ["JSESSIONID", "39ce7", "70a7c28f3de", "cf_clearance", "X-User"]
REQUIRED_KEYS    = ["DEEPSEEK_API_KEY", "CF_HANDLE"] + REQUIRED_COOKIES


def _try_load_agent():
    global _agent_ready, graph, build_prompt, check_onboarding, system_prompt
    if _agent_ready:
        return True
    missing = [k for k in REQUIRED_KEYS if not os.getenv(k)]
    if missing:
        return False
    try:
        from main import graph as g, build_prompt as bp, check_onboarding as co, system_prompt as sp
        graph         = g
        build_prompt  = bp
        check_onboarding = co
        system_prompt = sp
        _agent_ready  = True
        return True
    except Exception:
        return False


# ── Cookie 配置页 ──────────────────────────────────────────────

def save_config(api_key, cf_handle, jsessionid, key39, key70, cf_clearance, x_user):
    vals = {
        "DEEPSEEK_API_KEY": api_key,
        "CF_HANDLE":        cf_handle,
        "JSESSIONID":       jsessionid,
        "39ce7":            key39,
        "70a7c28f3de":      key70,
        "cf_clearance":     cf_clearance,
        "X-User":           x_user,
    }
    ENV_PATH.touch(exist_ok=True)
    for k, v in vals.items():
        if v:
            set_key(str(ENV_PATH), k, v.strip())
            os.environ[k] = v.strip()

    missing = [k for k, v in vals.items() if not v and not os.getenv(k)]
    if missing:
        return f"❌ 以下字段不能为空：{', '.join(missing)}", gr.update(visible=True), gr.update(visible=False)

    ok = _try_load_agent()
    if ok:
        return "✅ 配置已保存，Agent 加载成功！切换到「对话」标签开始使用。", gr.update(visible=True), gr.update(visible=False)
    else:
        return "⚠️ 配置已保存，但 Agent 加载失败，请检查依赖是否安装完整。", gr.update(visible=True), gr.update(visible=False)


def check_existing_config():
    """页面加载时检查是否已有完整配置"""
    missing = [k for k in REQUIRED_KEYS if not os.getenv(k)]
    if not missing:
        _try_load_agent()
        return "✅ 检测到已有完整配置，可直接使用对话功能。"
    return f"⚠️ 缺少配置：{', '.join(missing)}，请在下方填写。"


# ── 对话逻辑 ──────────────────────────────────────────────────

MAX_MESSAGES = 20

def _build_initial_messages():
    """构建初始 messages 列表"""
    prompt = build_prompt()
    full_system = system_prompt + "\n\n" + prompt
    msgs = [SystemMessage(full_system)]

    onboarding_prompt = check_onboarding()
    if onboarding_prompt is not None:
        # 首次使用，需要摸底
        onboarding_msgs = [
            SystemMessage(onboarding_prompt),
            HumanMessage("我准备好了，开始吧")
        ]
        return msgs, onboarding_msgs, True  # (main_msgs, onboarding_msgs, is_onboarding)
    return msgs, None, False


def _get_last_ai_text(messages):
    """从 LangGraph 返回的 messages 中提取最后一条 AI 文本"""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content
    return "（无回复）"


def chat(user_input, history, state):
    """
    state 结构:
    {
        "main_msgs": [...],
        "onboarding_msgs": [...] | None,
        "is_onboarding": bool,
        "initialized": bool
    }
    """
    if not _agent_ready and not _try_load_agent():
        history = history + [[user_input, "❌ Agent 未就绪，请先在「配置」标签填写完整信息。"]]
        return history, state

    # ── 首次进入，初始化 state ──
    if not state.get("initialized"):
        main_msgs, onboarding_msgs, is_onboarding = _build_initial_messages()
        state = {
            "main_msgs":       main_msgs,
            "onboarding_msgs": onboarding_msgs,
            "is_onboarding":   is_onboarding,
            "initialized":     True
        }

        # 如果需要摸底，先跑一次不带用户输入的摸底开场白
        if is_onboarding:
            try:
                result = graph.invoke({"messages": state["onboarding_msgs"]})
                state["onboarding_msgs"] = result["messages"]
                greeting = _get_last_ai_text(result["messages"])
                history = history + [["（进入系统）", greeting]]
                # 现在再处理用户刚发的第一条消息
            except Exception as e:
                history = history + [["（进入系统）", f"❌ 初始化失败：{e}"]]
                return history, state

    # ── 选择当前使用哪组 messages ──
    is_onboarding = state.get("is_onboarding", False)

    if is_onboarding:
        msgs = state["onboarding_msgs"]
        msgs.append(HumanMessage(user_input))
        try:
            result = graph.invoke({"messages": msgs})
            state["onboarding_msgs"] = result["messages"]
            reply = _get_last_ai_text(result["messages"])
        except CloudflareBlockError_handler(e := None):
            reply = f"❌ Cloudflare 拦截：cf_clearance 已失效，请在「配置」页更新 cookie。"
        except Exception as e:
            reply = f"❌ 出错：{e}"

        # 检查摸底是否完成（finish_onboarding 被调用后 onboarding_done 变为 true）
        from knowledge import check_onboarding as _co
        if _co() is None:
            state["is_onboarding"] = False  # 摸底结束，切换到正式模式

    else:
        msgs = state["main_msgs"]
        # 刷新 system prompt（知识库可能已更新）
        if msgs and isinstance(msgs[0], SystemMessage):
            from main import build_prompt as _bp, system_prompt as _sp
            msgs[0] = SystemMessage(_sp + "\n\n" + _bp())

        msgs.append(HumanMessage(user_input))
        try:
            result = graph.invoke({"messages": msgs})
            state["main_msgs"] = result["messages"]
            reply = _get_last_ai_text(result["messages"])
        except Exception as e:
            reply = f"❌ 出错：{e}"

        # 上下文压缩
        if len(state["main_msgs"]) > MAX_MESSAGES + 5:
            state["main_msgs"] = _compress(state["main_msgs"])

    history = history + [[user_input, reply]]
    return history, state


def _compress(messages):
    """简单截断策略：保留 system + 最近 MAX_MESSAGES 条"""
    system = [m for m in messages if isinstance(m, SystemMessage)]
    others = [m for m in messages if not isinstance(m, SystemMessage)]
    return system + others[-MAX_MESSAGES:]


# 占位符，避免 NameError
class CloudflareBlockError_handler:
    def __init__(self, e): pass
    def __bool__(self): return False


# ── Gradio UI ─────────────────────────────────────────────────

CSS = """
/* ── 全局 ── */
body { font-family: 'JetBrains Mono', 'Fira Code', monospace; }

.gradio-container {
    max-width: 900px !important;
    margin: 0 auto !important;
}

/* ── 标题区 ── */
#header {
    text-align: center;
    padding: 24px 0 8px;
    border-bottom: 2px solid #00e5ff;
    margin-bottom: 20px;
}
#header h1 {
    font-size: 1.8rem;
    color: #00e5ff;
    letter-spacing: 0.05em;
    margin: 0;
}
#header p {
    color: #888;
    font-size: 0.85rem;
    margin: 4px 0 0;
}

/* ── 聊天框 ── */
#chatbox .message.user {
    background: #1a2633 !important;
    border-left: 3px solid #00e5ff;
}
#chatbox .message.bot {
    background: #0d1117 !important;
    border-left: 3px solid #7c4dff;
}

/* ── 输入区 ── */
#input-row textarea {
    font-family: inherit;
    font-size: 0.9rem;
    background: #0d1117;
    color: #e0e0e0;
    border: 1px solid #2a3a4a;
}
#send-btn {
    background: #00e5ff !important;
    color: #000 !important;
    font-weight: bold;
    min-width: 80px;
}

/* ── 配置页 ── */
#config-status {
    padding: 10px 14px;
    border-radius: 6px;
    font-size: 0.85rem;
    background: #0d1117;
    border: 1px solid #2a3a4a;
    margin-bottom: 12px;
}
.section-label {
    color: #00e5ff;
    font-size: 0.78rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin: 16px 0 4px;
}
"""

with gr.Blocks( title="CF 陪练官") as demo:

    # ── 标题 ──
    gr.HTML("""
    <div id="header">
        <h1>⚡ CF 陪练官</h1>
        <p>基于 LangGraph 的 Codeforces 算法学习 Agent</p>
    </div>
    """)

    with gr.Tabs():

        # ═══════════════════ 对话标签 ═══════════════════
        with gr.Tab("💬 对话"):
            chatbot = gr.Chatbot(
                elem_id="chatbox",
                label="",
                height=520,
                show_label=False,
                avatar_images=(None, "🤖"),
            )

            with gr.Row(elem_id="input-row"):
                user_msg = gr.Textbox(
                    placeholder="输入代码或问题，Shift+Enter 换行，Enter 发送…",
                    lines=4,
                    max_lines=12,
                    show_label=False,
                    scale=9,
                )
                send_btn = gr.Button("发送", elem_id="send-btn", scale=1, variant="primary")

            gr.HTML("<p style='color:#555;font-size:0.78rem;text-align:center;margin-top:6px;'>提交代码时请直接粘贴，无需加代码块标记</p>")

            # 状态
            chat_state = gr.State({})

            def submit(msg, history, state):
                if not msg.strip():
                    return history, state, ""
                h, s = chat(msg.strip(), history, state)
                return h, s, ""

            send_btn.click(submit, [user_msg, chatbot, chat_state], [chatbot, chat_state, user_msg])
            user_msg.submit(submit, [user_msg, chatbot, chat_state], [chatbot, chat_state, user_msg])

        # ═══════════════════ 配置标签 ═══════════════════
        with gr.Tab("⚙️ 配置"):
            status_text = gr.Textbox(
                value=check_existing_config,
                label="当前状态",
                interactive=False,
                elem_id="config-status",
                lines=1,
            )

            gr.HTML("<div class='section-label'>API 配置</div>")
            with gr.Row():
                inp_apikey  = gr.Textbox(label="DEEPSEEK_API_KEY", type="password",
                                          placeholder="sk-…", value=lambda: os.getenv("DEEPSEEK_API_KEY",""))
                inp_handle  = gr.Textbox(label="CF_HANDLE（Codeforces 用户名）",
                                          placeholder="your_cf_username", value=lambda: os.getenv("CF_HANDLE",""))

            gr.HTML("<div class='section-label'>Codeforces Cookie（从浏览器 F12 → Application → Cookies 获取）</div>")

            with gr.Row():
                inp_jsession = gr.Textbox(label="JSESSIONID",  type="password", value=lambda: os.getenv("JSESSIONID",""))
                inp_39       = gr.Textbox(label="39ce7",       type="password", value=lambda: os.getenv("39ce7",""))
                inp_70       = gr.Textbox(label="70a7c28f3de", type="password", value=lambda: os.getenv("70a7c28f3de",""))
            with gr.Row():
                inp_cf       = gr.Textbox(label="cf_clearance", type="password", value=lambda: os.getenv("cf_clearance",""),
                                           scale=2)
                inp_xuser    = gr.Textbox(label="X-User",        type="password", value=lambda: os.getenv("X-User",""),
                                           scale=1)

            gr.HTML("""
            <div style='background:#0d1117;border:1px solid #2a3a4a;border-radius:6px;
                        padding:12px 16px;font-size:0.82rem;color:#888;margin:12px 0;line-height:1.8;'>
                <b style='color:#00e5ff'>获取 Cookie 步骤：</b><br>
                1. 浏览器登录 codeforces.com<br>
                2. 按 F12 → Application → Storage → Cookies → https://codeforces.com<br>
                3. 找到上面每个字段，复制 Value 粘贴到对应输入框<br>
                4. <b style='color:#ff9800'>cf_clearance 有效期约 24 小时，失效后需重新获取</b>
            </div>
            """)

            save_btn    = gr.Button("💾 保存配置", variant="primary")
            save_result = gr.Textbox(label="保存结果", interactive=False, lines=1)

            save_btn.click(
                save_config,
                inputs=[inp_apikey, inp_handle, inp_jsession, inp_39, inp_70, inp_cf, inp_xuser],
                outputs=[save_result, gr.State(), gr.State()],
            )

        # ═══════════════════ 说明标签 ═══════════════════
        with gr.Tab("📖 使用说明"):
            gr.Markdown("""
## 快速开始

1. **配置页** 填入 DeepSeek API Key、CF 用户名和浏览器 Cookie，点击保存
2. **对话页** 直接开始对话，首次使用会自动进行算法摸底

---

## 支持的指令

| 指令 | 示例 |
|------|------|
| 要一道题 | `给我一道 dp 中等题` |
| 提交代码 | 直接粘贴代码并发送 |
| 问算法 | `为什么 Dijkstra 不能处理负权边？` |
| 跳过当前题 | `跳过` 或 `不会` |
| 退出摸底 | 摸底完成后自动切换正式模式 |

---

## 支持的语言

`python` · `pypy` · `cpp17` · `cpp20` · `java` · `c`

发送代码时请在开头注明语言，例如：
```
语言：cpp17
（粘贴代码）
```

---

## 注意事项

- `cf_clearance` 约 **24 小时**过期，过期后请重新获取并在配置页更新
- 每道题最多提交 **3 次**，超过后需完成前置算法才能解锁
- 本工具仅供个人学习使用
            """)


# ── 启动 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    # 尝试预加载 agent
    _try_load_agent()
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        css=CSS,
        theme=gr.themes.Base(
            primary_hue="cyan",
            secondary_hue="purple",
            neutral_hue="slate",
        ),
        share=False,
        inbrowser=True,
    )