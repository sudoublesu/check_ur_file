#!/usr/bin/env python3
"""
app.py - 规划文件校对 Streamlit Web 应用

Usage:
    streamlit run app.py
"""

import os
import tempfile
from pathlib import Path

import streamlit as st

# ── 页面配置（必须在所有 st.* 调用之前）────────────────────────────
st.set_page_config(
    page_title="规划文件校对工具",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 全局样式 ───────────────────────────────────────────────────────
st.markdown("""
<style>
/* 下载按钮组靠左对齐 */
.stDownloadButton { display: inline-block; margin-right: 8px; }
/* 指标卡片稍加间距 */
[data-testid="metric-container"] { background: #f8f9fa; border-radius: 8px; padding: 12px; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
#  侧边栏：设置
# ══════════════════════════════════════════════════════════════════

with st.sidebar:
    st.title("⚙️ 校对设置")
    st.divider()

    # AI 模型选择（必选）
    ai_choice = st.radio(
        "选择 AI 模型",
        ["DeepSeek", "Gemini", "Claude"],
        index=0,
        help="AI 模型负责深度校对，发现错别字、数据矛盾、概念错误、逻辑问题等",
    )

    MODEL_MAP = {
        "DeepSeek": "deepseek",
        "Gemini": "gemini",
        "Claude": "claude",
    }
    selected_model = MODEL_MAP[ai_choice]

    # 对应 API Key 输入框
    if selected_model:
        st.divider()

        ENV_VARS = {
            "deepseek": ("DEEPSEEK_API_KEY", "sk-..."),
            "gemini": ("GEMINI_API_KEY", "AIzaSy-..."),
            "claude": ("ANTHROPIC_API_KEY", "sk-ant-..."),
        }
        env_var, placeholder = ENV_VARS[selected_model]

        # 检查 .env 是否已配置（不显示真实 Key，只提示状态）
        env_configured = bool(os.environ.get(env_var, ""))
        if env_configured:
            st.caption(f"✅ {env_var} 已在服务器配置，所有用户共用")
        else:
            st.caption(f"⚠️ {env_var} 未配置")
            # 未配置时才显示输入框（仅本 session 有效，不影响其他用户）
            api_key_input = st.text_input(
                f"{ai_choice} API Key（本次有效）",
                type="password",
                placeholder=placeholder,
                help=f"仅对你当前的请求有效，不影响其他用户。\n"
                     f"如需长期使用，请在服务器 .env 文件中配置 {env_var}=...",
            )
            # 存入 session_state，不写入 os.environ
            if api_key_input:
                st.session_state["_session_api_key"] = (env_var, api_key_input)
            else:
                st.session_state.pop("_session_api_key", None)

    st.divider()
    st.caption("项目目录约定")
    st.code("input/   → 待校对文件\noutput/  → 报告 & 批注版\ntemp/    → 中间文件", language=None)


# ══════════════════════════════════════════════════════════════════
#  主区域
# ══════════════════════════════════════════════════════════════════

st.title("规划文件校对工具")
st.caption("上海市控制性详细规划（控规）文件智能校对系统 · 支持 .docx / .pdf")

uploaded_file = st.file_uploader(
    "上传文件",
    type=["docx", "pdf"],
    label_visibility="collapsed",
)

# 文件信息 + 开始按钮
col_info, col_btn = st.columns([4, 1])
with col_info:
    if uploaded_file:
        st.info(
            f"📄 **{uploaded_file.name}**　　"
            f"{uploaded_file.size / 1024:.0f} KB　　"
            f"AI: {ai_choice}"
        )
with col_btn:
    start = st.button(
        "开始校对",
        type="primary",
        disabled=not uploaded_file,
        use_container_width=True,
    )


# ══════════════════════════════════════════════════════════════════
#  执行校对
# ══════════════════════════════════════════════════════════════════

if start and uploaded_file:
    st.session_state.pop("result", None)   # 清除上次结果

    # 保存上传文件到临时路径
    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(uploaded_file.getbuffer())
        tmp_path = tmp.name

    # 进度 UI
    progress_bar = st.progress(0, text="准备中…")

    def progress_cb(step: str, pct: int):
        progress_bar.progress(pct / 100, text=step)

    # 若用户在侧边栏输入了 Key，临时注入环境变量（用完即还原）
    _injected_key = st.session_state.pop("_session_api_key", None)
    if _injected_key:
        _env_var, _env_val = _injected_key
        _orig_val = os.environ.get(_env_var)
        os.environ[_env_var] = _env_val

    try:
        from pipeline import run_pipeline
        result = run_pipeline(
            tmp_path,
            progress_cb=progress_cb,
            ai_model=selected_model,
        )
        st.session_state["result"] = result
        st.session_state["orig_name"] = uploaded_file.name
        progress_bar.progress(1.0, text="完成！")
    except EnvironmentError as e:
        progress_bar.empty()
        st.error(f"API Key 未配置：{e}")
    except Exception as e:
        progress_bar.empty()
        st.error(f"校对失败：{e}")
        st.exception(e)
    finally:
        # 还原临时注入的 Key，不影响其他用户
        if _injected_key:
            if _orig_val is None:
                os.environ.pop(_env_var, None)
            else:
                os.environ[_env_var] = _orig_val
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ══════════════════════════════════════════════════════════════════
#  结果展示
# ══════════════════════════════════════════════════════════════════

if "result" in st.session_state:
    result = st.session_state["result"]
    orig_name = st.session_state.get("orig_name", "文件")
    stem = Path(orig_name).stem

    issues      = result["issues"]
    errors      = [i for i in issues if i.get("severity") == "error"]
    warnings    = [i for i in issues if i.get("severity") == "warning"]
    suggestions = [i for i in issues if i.get("severity") == "suggestion"]
    ai_issues   = [i for i in issues if i.get("source") == "ai"]

    st.divider()

    # ── 统计卡片 ──────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("问题总数",     len(issues))
    c2.metric("🔴 错误",     len(errors),      help="必须修改")
    c3.metric("🟡 警告",     len(warnings),    help="建议修改")
    c4.metric("💡 建议",     len(suggestions), help="可考虑优化")
    c5.metric("🤖 AI 发现",  len(ai_issues),   help="AI 深度校对新增问题")

    # AI 总结
    if result.get("ai_summary"):
        st.info(f"**AI 评估**：{result['ai_summary']}")

    # ── 下载按钮（常驻）─────────────────────────────────────────────
    dl1, dl2, _ = st.columns([1, 1, 3])
    report_path_obj = Path(result["report_path"])
    if report_path_obj.exists():
        dl1.download_button(
            label="⬇ 校对报告 (.md)",
            data=report_path_obj.read_bytes(),
            file_name=f"{stem}_校对报告.md",
            mime="text/markdown",
            use_container_width=True,
        )
    docx_path = result.get("docx_path")
    if docx_path and Path(docx_path).exists():
        dl2.download_button(
            label="⬇ 批注版 Word (.docx)",
            data=Path(docx_path).read_bytes(),
            file_name=f"{stem}_批注.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )

    st.divider()

    # ── 标签页 ────────────────────────────────────────────────────
    tab_report, tab_numbers = st.tabs(["📋 校对报告", "🔢 数字指标"])

    with tab_report:
        report_path = Path(result["report_path"])
        if report_path.exists():
            report_text = report_path.read_text(encoding="utf-8")
            st.markdown(report_text)
        else:
            st.warning("报告文件未找到。")

    with tab_numbers:
        numbers = result.get("numbers", {})
        number_issues = result.get("number_issues", [])

        # 校验问题（如有）
        if number_issues:
            st.warning(f"**数字校验发现 {len(number_issues)} 项问题：**")
            SICON = {"error": "🔴", "warning": "🟡", "suggestion": "💡"}
            for ni in number_issues:
                icon = SICON.get(ni.get("severity", "warning"), "🟡")
                loc  = result.get("location_map", {}).get(ni.get("para_index", -1), f"第{ni.get('para_index')}段")
                st.markdown(f"{icon} **{loc}**：{ni.get('comment', '')}")
            st.divider()

        TYPE_LABELS = {
            "areas":       "面积",
            "ratios":      "容积率 / 建筑密度 / 绿地率",
            "years":       "年份",
            "populations": "人口",
            "others":      "其他",
        }
        has_any = any(v for v in numbers.values())
        if has_any:
            for cat, items in numbers.items():
                if not items:
                    continue
                label = TYPE_LABELS.get(cat, cat)
                # 找出该类别中有校验问题的段落
                flagged_paras = {
                    ni.get("para_index")
                    for ni in number_issues
                    if ni.get("matched") and any(
                        ni.get("matched") in (i.get("context", "") or "")
                        for i in items
                    )
                }
                flag = " ⚠️" if flagged_paras else ""
                with st.expander(f"{label}（{len(items)} 处）{flag}", expanded=(cat == "ratios")):
                    rows = [
                        {
                            "数值": i.get("matched") or i.get("value", ""),
                            "上下文": i.get("context", "")[:60],
                            "段落": i.get("para", "—"),
                        }
                        for i in items
                    ]
                    st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("未提取到数字指标。")
