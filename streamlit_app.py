"""致壹 · 数据分析智能体界面。

视觉沿用 flowmind-m0.html 的首界面（Linear 风格三栏语言）：
左侧导航、中部 Hero + 最近任务/最近文件、底部对话输入。
所有展示内容均来自真实上传文件与真实 Agent 执行结果，不做任何伪造。

启动：
    python -m streamlit run streamlit_app.py
    （监听地址/端口见 .streamlit/config.toml，默认 0.0.0.0:8501；
      可用 STREAMLIT_SERVER_ADDRESS / STREAMLIT_SERVER_PORT 覆盖）
"""
from __future__ import annotations

import html
import json
import os
import sys
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import db
from app import edu_ui
from app.config import (
    ROOT, PROJECT_DIR,
    UPLOAD_DIR, ALLOWED_EXT, DOC_EXT, UPLOAD_EXT, PARSER_TOOL_TYPE,
    LLM_BASE_URL, LLM_MODEL, LLM_API_KEY,
    ZHIPU_BASE_URL, ZHIPU_API_KEY, ZHIPU_MODEL,
)
from app.loader import read_file, quality_gate, merge_loads
from app.tools import (
    register, clear_registry, _REGISTRY,
    register_document, clear_documents, get_documents,
    clear_searches, get_searches, set_output_dir,
)
from app.zhipu_parser import parse_sync as parse_document_sync
from app.zhipu_search import web_search as _zhipu_web_search, ERROR_CODES as _ZHIPU_SEARCH_ERRORS
from app import zhipu_media
from app.intent import classify


st.set_page_config(
    page_title="致壹 教育工作台",
    page_icon="🟣",
    layout="wide",
    initial_sidebar_state="expanded",
)

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 首页快捷卡片图标（复用 Streamlit 自带的 Material Symbols Rounded 图标字体；
# 内联 SVG 会被 st.html 的净化逻辑过滤掉，故改用字体连字）
_ICONS = {
    "book": "menu_book",
    "tool": "construction",
    "chat": "forum",
    "check": "fact_check",
    "lib": "library_books",
    "chart": "insights",
    "doc": "assignment",
    "star": "star",
    "clock": "history",
}


# ---------------------------------------------------------------------------
# 全局样式（移植 flowmind-m0.html 的设计变量）
# ---------------------------------------------------------------------------
CSS = """
<style>
:root{ /* SaaS 层在后面覆盖所有 token */ }

/* ---------- 亮色主题（设置页切换）：只覆盖 token，组件规则共用 ---------- */
.fm-thememode{display:none}



















html, body, .stApp, [data-testid="stAppViewContainer"]{
  background:var(--bg); color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
}
html, body, .stApp{font-size:12.5px; line-height:1.45; -webkit-font-smoothing:antialiased}

/* 隐藏 Streamlit 外壳 */
#MainMenu, footer, header[data-testid="stHeader"], [data-testid="stToolbar"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"], .stDeployButton{display:none !important}
[data-testid="stMainBlockContainer"], .block-container{
  padding:0 24px 130px 24px; max-width:none; width:100%; margin:0 auto;
}

/* ---------- 侧边栏（固定，可收起 / 展开） ---------- */
section[data-testid="stSidebar"]{
  background:var(--panel-2); border-right:1px solid var(--line);
  width:236px !important; min-width:236px !important; max-width:236px !important;
  position:fixed !important; top:0; left:0; bottom:0; height:100vh;
  overflow:hidden; z-index:1000; transform:none !important;
  display:flex !important; visibility:visible !important;
  transition:width .18s ease;
}
/* Streamlit 在窄视口/缩放后会自行把侧栏标记为收起（aria-expanded=false），
   这里强制保持可见，避免侧栏整体消失 */
section[data-testid="stSidebar"][aria-expanded="false"]{
  display:flex !important; visibility:visible !important;
  transform:none !important; margin-left:0 !important;
}
/* 固定侧栏脱离文档流后，主内容容器（Streamlit 1.50 的 stAppViewContainer 是 absolute）
   需要 left + width 让出侧栏宽度，否则会被侧栏盖住 */
[data-testid="stAppViewContainer"]{
  left:236px !important;
  width:calc(100% - 236px) !important;
  max-width:calc(100% - 236px) !important;
}
/* 收起：侧栏缩为 52px 竖条，主内容容器随之让出空间 */
[data-testid="stAppViewContainer"]:has(.st-key-sbclosed) section[data-testid="stSidebar"]{
  width:52px !important; min-width:52px !important; max-width:52px !important;
}
[data-testid="stAppViewContainer"]:has(.st-key-sbclosed){
  left:52px !important; width:calc(100% - 52px) !important; max-width:calc(100% - 52px) !important;
}
[data-testid="stAppViewContainer"]:has(.st-key-sbclosed) .st-key-sbhead{border-bottom:0; padding-bottom:0}
[data-testid="stAppViewContainer"]:has(.st-key-sbclosed) .st-key-sbhead [data-testid="stHorizontalBlock"]{
  flex-direction:column; align-items:center; gap:10px;
}
[data-testid="stAppViewContainer"]:has(.st-key-sbclosed) .st-key-sbhead [data-testid="stColumn"]{
  width:100% !important; flex:0 0 auto !important; min-width:0 !important;
}
[data-testid="stAppViewContainer"]:has(.st-key-sbclosed) .st-key-sbhead .stButton{width:24px; margin:0 auto}
/* 收起后只保留展开箭头，品牌与其余内容全部隐藏 */
[data-testid="stAppViewContainer"]:has(.st-key-sbclosed) .fm-brand,
[data-testid="stAppViewContainer"]:has(.st-key-sbclosed) .fm-navlabel,
[data-testid="stAppViewContainer"]:has(.st-key-sbclosed) .st-key-nav,
[data-testid="stAppViewContainer"]:has(.st-key-sbclosed) .st-key-sb-newproj,
[data-testid="stAppViewContainer"]:has(.st-key-sbclosed) .fm-sidefoot,
[data-testid="stAppViewContainer"]:has(.st-key-sbclosed) section[data-testid="stSidebar"] [data-testid="stExpander"]{
  display:none !important;
}
/* 手机级窄视口：侧栏自动收成 52px 竖条，避免主内容被挤成一条缝 */
@media (max-width:480px){
  section[data-testid="stSidebar"]{
    width:52px !important; min-width:52px !important; max-width:52px !important;
  }
  [data-testid="stAppViewContainer"]{
    left:52px !important; width:calc(100% - 52px) !important; max-width:calc(100% - 52px) !important;
  }
  .st-key-sbhead{border-bottom:0; padding-bottom:0}
  .st-key-sbhead [data-testid="stHorizontalBlock"]{flex-direction:column; align-items:center; gap:10px}
  .st-key-sbhead [data-testid="stColumn"]{width:100% !important; flex:0 0 auto !important; min-width:0 !important}
  .st-key-sbhead .stButton{width:24px; margin:0 auto}
  .fm-brand, .fm-navlabel, .st-key-nav, .st-key-sb-newproj, .fm-sidefoot,
  section[data-testid="stSidebar"] [data-testid="stExpander"]{display:none !important}
}

/* 侧栏头部：品牌 + 收起开关同一行 */
.st-key-sbhead{border-bottom:1px solid var(--line); margin-bottom:4px; padding-bottom:4px}
.st-key-sbhead [data-testid="stHorizontalBlock"]{align-items:center; gap:6px}
.st-key-sbhead [data-testid="stColumn"]{min-width:0}
.st-key-sbhead .stButton button{
  width:24px; height:24px; min-height:24px; padding:0; border-radius:6px;
  display:flex; align-items:center; justify-content:center;
  background:transparent; border:0; box-shadow:none; color:var(--text-3);
}
.st-key-sbhead .stButton button:hover{background:var(--hover-bg); color:var(--text)}
.st-key-sbhead .stButton button [data-testid="stIconMaterial"]{font-size:16px}
/* 收起状态标记：不占布局空间 */
.st-key-sbclosed{height:0 !important; min-height:0 !important; margin:0 !important;
  padding:0 !important; overflow:hidden}
/* 隐藏 Streamlit 原生侧栏开关，统一用上面的按钮 */
[data-testid="stSidebarCollapseButton"], [data-testid="stSidebarCollapsedControl"]{display:none !important}
/* 隐藏 Streamlit 默认侧栏头部（致壹品牌区，会导致顶部 47px 留白） */
[data-testid="stSidebarHeader"]{display:none !important}
[data-testid="stSidebarContent"]{height:100vh; overflow:hidden; padding:0 !important; margin:0 !important}
/* 侧栏改为纵向 flex：品牌贴顶、导航区占满并滚动、用户区钉底 */
[data-testid="stSidebarUserContent"]{
  padding:0 2px 6px 2px !important; height:100vh !important; margin:0 !important;
  display:flex !important; flex-direction:column !important; overflow:hidden !important;
}
/* stSidebarUserContent > emotion 包装 div > stVerticalBlock：把 flex 传下去 */
[data-testid="stSidebarUserContent"] > div{
  flex:1 1 auto !important; min-height:0 !important;
  display:flex !important; flex-direction:column !important;
}
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"]{
  flex:1 1 auto !important; min-height:0 !important; padding:0 !important; gap:0 !important;
  display:flex !important; flex-direction:column !important; overflow:hidden !important;
}
/* 品牌区固定在顶端 */
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"]:has(.st-key-sbhead){
  flex:0 0 auto !important; padding-top:10px !important;
}
/* 新建任务按钮：不伸缩 */
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"]:has(.st-key-sb-newproj){
  flex:0 0 auto !important;
}
/* 导航区占据剩余高度，内容过多时内部滚动 */
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"]:has(.st-key-nav){
  flex:1 1 0 !important; min-height:0 !important;
  overflow-y:auto !important; overflow-x:hidden !important;
}
[data-testid="stSidebarUserContent"] .st-key-nav{min-height:0 !important; overflow:visible !important}
[data-testid="stSidebarUserContent"] .st-key-nav [data-testid="stVerticalBlock"]{min-height:0 !important}
/* 本地用户区钉在侧栏底部 */
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:has(.fm-sidefoot){
  flex:0 0 auto !important; margin-top:auto !important;
}

/* 品牌区 */
.fm-brand{display:flex;align-items:center;gap:10px;padding:0 0 0 4px}
.fm-mark{width:26px;height:26px;border-radius:6px;background:var(--accent);
  display:grid;place-items:center;color:#fff;font-weight:700;font-size:12px;letter-spacing:-.3px}
.fm-brand-name{font-weight:600;font-size:13.5px;letter-spacing:-.1px;line-height:1.25;color:var(--text)}
.fm-brand-sub{font-size:10.5px;color:var(--text-3);line-height:1.3}

/* 分组标题 */
.fm-navlabel{font-size:10px;letter-spacing:.1em;color:var(--text-3);
  padding:9px 9px 4px;font-weight:600}

/* 侧栏导航按钮 */
.st-key-nav [data-testid="stVerticalBlock"], .st-key-nav[data-testid="stVerticalBlock"]{gap:2px}
.st-key-nav .stButton>button{
  width:100%; justify-content:flex-start; text-align:left; gap:8px;
  background:transparent !important; border:1px solid transparent !important;
  box-shadow:none !important; padding:6px 9px !important; border-radius:8px;
  min-height:29px; font-size:12.5px; font-weight:500; color:var(--text-2) !important;
}
.st-key-nav .stButton>button p{font-size:12.5px; font-weight:500; margin:0}
.st-key-nav .stButton>button [data-testid="stIconMaterial"]{font-size:16px; opacity:.7}
.st-key-nav .stButton>button:hover{background:var(--hover-bg) !important; color:var(--text) !important}
.st-key-nav .stButton>button[kind="primary"]{
  background:var(--accent-soft) !important; border-color:var(--accent-line) !important;
  color:var(--accent) !important; font-weight:600;
}
.st-key-nav .stButton>button[kind="primary"] [data-testid="stIconMaterial"]{opacity:1}
.st-key-nav .stButton>button[kind="primary"]:hover{background:var(--hover-bg) !important; color:var(--hover-text) !important}

/* AI 助手：字号 / 字重 / 高度与「新建任务」一致 */
#root [class*="st-key-navbtn_AI"] .stButton>button{
  min-height:32px !important; padding:6px 9px !important;
}
#root [class*="st-key-navbtn_AI"] .stButton>button,
#root [class*="st-key-navbtn_AI"] .stButton>button p{
  font-size:13.5px !important; font-weight:600 !important;
}

/* 侧栏分区标题（工作区 / 默认 / 项目，可展开收起） */
.st-key-ws_toggle .stButton>button,
.st-key-df_toggle .stButton>button,
.st-key-pj_toggle .stButton>button{
  width:100%; justify-content:flex-start; min-height:auto;
  background:transparent !important; border:0 !important; box-shadow:none !important;
  padding:6px 9px !important; border-radius:0;
}
.st-key-ws_toggle .stButton>button p,
.st-key-df_toggle .stButton>button p,
.st-key-pj_toggle .stButton>button p{
  font-size:10px; letter-spacing:.1em; font-weight:600; color:var(--text-3);
}
.st-key-ws_toggle .stButton>button:hover,
.st-key-df_toggle .stButton>button:hover,
.st-key-pj_toggle .stButton>button:hover{background:transparent !important}
.st-key-ws_toggle .stButton>button:hover p,
.st-key-df_toggle .stButton>button:hover p,
.st-key-pj_toggle .stButton>button:hover p{color:var(--text)}

/* 侧栏模型配置 */
section[data-testid="stSidebar"] [data-testid="stExpander"] details{
  background:var(--panel-3); border:1px solid var(--line) !important; border-radius:6px;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary{font-size:12px;color:var(--text-2)}

/* 侧栏顶部「新建项目」按钮与输入框 */
.st-key-sb-newproj{margin-bottom:6px}
.st-key-sb-newproj .stButton>button{
  width:100%; justify-content:flex-start; gap:6px; min-height:32px;
  background:#0e639c !important;
  border:1px solid #1177bb !important;
  border-radius:6px; box-shadow:none !important;
  color:#fff !important; font-size:12px; font-weight:600; padding:6px 9px !important;
}
.st-key-sb-newproj .stButton>button p{font-size:12px; font-weight:600; margin:0; color:#fff !important}
.st-key-sb-newproj .stButton>button [data-testid="stIconMaterial"]{color:#fff !important}
.st-key-sb-newproj .stButton>button:hover{
  background:#1177bb !important;
  border-color:var(--accent-hover) !important; color:#fff !important;
}
.st-key-sb-newproj [data-testid="stCaptionContainer"] p{font-size:11px; color:var(--text-3); margin:2px 0 0}
.st-key-sb-newproj [data-testid="stVerticalBlock"]{gap:6px}

/* 任务识别结果横幅 */
.fm-routebar{
  display:flex; align-items:flex-start; gap:10px;
  background:var(--accent-soft); border:1px solid var(--accent-line); border-radius:6px;
  padding:10px 12px; margin:0 0 12px;
}
.fm-route-b{flex:1; min-width:0}
.fm-route-t{font-size:12.5px; color:var(--text); line-height:1.5; word-break:break-word}
.fm-route-s{font-size:11px; color:var(--text-3); margin-top:3px}

/* 侧栏底部用户 */.fm-sidefoot{display:flex;align-items:center;gap:9px;border-top:1px solid var(--line);margin-top:8px;padding:8px 4px 0}
.fm-av{width:24px;height:24px;border-radius:50%;background:var(--accent-soft);color:var(--accent);
  display:grid;place-items:center;font-size:10.5px;font-weight:700}

/* 项目行操作按钮：收紧与上方文字的间距 */
div[class*="st-key-projops_"]{margin-top:-8px}
div[class*="st-key-projops_"] .stButton>button{min-height:30px; font-size:12px; padding:2px 8px}

/* 附件上传：与 5 个快捷图标同款的小圆点（把上传组件压成圆形按钮，尺寸随容器自适应） */
.st-key-cpattach, .st-key-cpattach [data-testid="stFileUploader"],
.st-key-cpattach [data-testid="stFileUploaderDropzone"]{width:var(--chip, 32px)}
.st-key-cpattach [data-testid="stFileUploaderDropzone"]{
  position:relative; width:var(--chip, 32px); height:var(--chip, 32px); min-height:var(--chip, 32px) !important;
  padding:0 !important; border:0; border-radius:50%;
  background:transparent; box-shadow:none;
  display:flex; align-items:center; justify-content:center; overflow:hidden;
}
.st-key-cpattach [data-testid="stFileUploaderDropzone"]:hover{background:var(--hover-bg)}
.st-key-cpattach [data-testid="stFileUploaderDropzoneInstructions"]{
  position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
  pointer-events:none;
}
.st-key-cpattach [data-testid="stFileUploaderDropzoneInstructions"] > div{display:none}
.st-key-cpattach [data-testid="stFileUploaderDropzoneInstructions"] > span{
  display:flex !important; align-items:center; justify-content:center;
}
.st-key-cpattach [data-testid="stFileUploaderDropzoneInstructions"] svg{
  width:calc(var(--chip, 32px) * .5); height:calc(var(--chip, 32px) * .5); color:var(--text-2);
}
.st-key-cpattach [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"]{
  position:absolute; inset:0; width:var(--chip, 32px); height:var(--chip, 32px); padding:0; margin:0;
  border:0; background:transparent !important; opacity:0; cursor:pointer;
}
.st-key-cpattach [data-testid="stFileUploaderFileList"]{display:none}
/* 拖拽文件到输入卡片时的提示态 */
.st-key-herobox.fm-drop{
  border-color:var(--accent) !important; border-style:dashed;
  box-shadow:0 0 0 1px var(--focus-ring) !important;
}
/* 拖拽文件到胶囊输入栏时的提示态 */
.st-key-composer.fm-drop{
  border-color:var(--accent) !important; border-style:dashed;
  box-shadow:0 0 0 1px var(--focus-ring) !important;
}

/* 通用面板卡片 */
.st-key-panel{
  background:var(--panel-3); border:1px solid var(--line); border-radius:8px;
  box-shadow:none; padding:12px 14px; margin-bottom:10px;
}

/* ---------- 通用组件 ---------- */
.fm-h1{font-size:28px;letter-spacing:-.6px;margin:0 0 16px;font-weight:600;text-align:center}
.fm-hero-p{color:var(--text-2);margin:6px 0 14px;font-size:13px;max-width:560px}
.fm-sec-title{font-size:12px;font-weight:600;letter-spacing:-.1px;margin:2px 0 8px;color:var(--text)}
.fm-tag{display:inline-flex;align-items:center;gap:5px;font-size:11px;padding:1px 6px;
  border-radius:4px;border:1px solid var(--line);background:var(--panel-3);color:var(--text-2);font-weight:500}
.fm-tag.ok{background:var(--ok-soft);border-color:rgba(137,209,133,.35);color:var(--ok)}
.fm-tag.warn{background:var(--warn-soft);border-color:rgba(204,167,0,.35);color:var(--warn)}
.fm-tag.err{background:var(--err-soft);border-color:rgba(241,76,76,.35);color:var(--err)}
.fm-tag.acc{background:var(--accent-soft);border-color:var(--accent-line);color:var(--accent)}
.fm-dot{width:6px;height:6px;border-radius:50%;background:currentColor;display:inline-block}
.fm-kbd{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10.5px;border:1px solid var(--line-strong);
  border-bottom-width:2px;border-radius:4px;padding:1px 4px;color:var(--text-3);background:var(--panel-3)}
.fm-muted{color:var(--text-3);font-size:11.5px}
.fm-list-item{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--line)}
.fm-list-item:last-child{border-bottom:0;padding-bottom:0}
.fm-list-item:first-child{padding-top:0}
.fm-fi{width:26px;height:26px;border-radius:7px;background:var(--panel-2);border:1px solid var(--line);
  display:grid;place-items:center;flex:0 0 26px;color:var(--text-2)}
.fm-fi svg{width:13px;height:13px;stroke-width:1.8}
.fm-li-t{font-size:12.5px;font-weight:520;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text)}
.fm-li-s{font-size:11px;color:var(--text-3)}
.fm-ftag{font-size:9.5px;font-weight:700;letter-spacing:.04em;padding:3px 5px;border-radius:5px;
  background:var(--ok-soft);color:var(--ok);flex:0 0 auto}
.fm-ftag.csv{background:var(--accent-soft);color:var(--accent)}
.fm-empty{text-align:center;padding:22px 12px;color:var(--text-3);font-size:11.5px}
.fm-cardhead{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.fm-cardhead h2{font-size:14px;margin:0;font-weight:600;letter-spacing:-.1px}
.fm-cardhead .r{margin-left:auto;font-size:11px;color:var(--text-3)}
.fm-me{display:flex;justify-content:flex-end;margin:8px 0}
.fm-me .b{background:var(--panel-2);border:1px solid var(--line);padding:7px 11px;
  border-radius:9px;font-size:12.5px;max-width:78%;line-height:1.6}

/* ---------- 教育模式：数据表格 / 模式切换 ---------- */
.fm-etable{width:100%;border-collapse:collapse;font-size:12px;margin:2px 0 6px}
.fm-etable th{text-align:left;font-weight:600;color:var(--text-2);font-size:11px;
  padding:5px 8px;border-bottom:1px solid var(--line);white-space:nowrap;background:var(--panel-2)}
.fm-etable td{padding:6px 8px;border-bottom:1px solid var(--line);color:var(--text);vertical-align:top}
.fm-etable tr:last-child td{border-bottom:0}
.st-key-edu_mode [data-testid="stRadio"]{margin:2px 0 6px}
.st-key-edu_mode [data-testid="stRadio"] > label{display:none}
.st-key-edu_mode [role="radiogroup"]{gap:6px;flex-wrap:nowrap}
.st-key-edu_mode [role="radiogroup"] label{font-size:11.5px;padding:3px 6px}

/* ---------- Hero（按 TRAE 首页 UI 规范重做） ---------- */
[data-testid="stMainBlockContainer"]:has(.st-key-herowrap){padding-bottom:24px}

.st-key-herowrap{
  min-height:calc(100vh - 150px);
  display:flex; flex-direction:column; justify-content:center; align-items:center;
}
.st-key-herowrap > [data-testid="stVerticalBlock"]{
  width:100%; display:flex; flex-direction:column; justify-content:center; align-items:center;
}
.st-key-hero{
  /* 紧凑版：侧栏右侧区域内水平居中，宽度上限 760px */
  width:100%; max-width:min(760px, 88vw); margin:0 auto;
  background:transparent; border:0; box-shadow:none; padding:0;
}
.fm-h1{
  margin:0 0 36px; text-align:center; white-space:nowrap;
  font-size:clamp(24px, 1.4vw + 12px, 38px); font-weight:600; line-height:1.2; letter-spacing:-.4px;
  color:#e5e5e5;
}
/* 输入卡：1000 宽、16 圆角、1px 描边、与页面同色 */
.st-key-herobox{
  background:transparent; border:1px solid #383838; border-radius:16px;
  padding:20px 24px 0; min-height:0;
  display:flex; flex-direction:column; justify-content:flex-start;
  transition:border-color .12s;
}
.st-key-herobox:focus-within{border-color:#4a4a4a; box-shadow:none}
.st-key-promptbox{
  position:relative; padding-bottom:46px;
  background:transparent; border:0; padding-left:0; padding-right:0; box-shadow:none;
}
.st-key-promptbox [data-testid="stTextArea"] label{display:none}
.st-key-promptbox [data-testid="stTextInput"] > div,
.st-key-promptbox [data-baseweb="input"],
.st-key-promptbox [data-baseweb="base-input"],
.st-key-promptbox [data-baseweb="textarea"],
.st-key-promptbox [data-testid="stTextArea"] > div{
  border:0 !important; border-bottom:0 !important; box-shadow:none !important;
  background:transparent !important;
}
.st-key-promptbox textarea{
  border:0 !important; box-shadow:none !important; background:transparent !important;
  padding:0 !important;
  /* 字号、行高、最小高度随窗口宽度/高度缩放 */
  font-size:clamp(14px, 0.35vw + 9px, 17px) !important;
  line-height:1.55 !important;
  /* 高度跟随内容与页面缩放：优先用原生 field-sizing，旧内核回退到 JS 计算 */
  field-sizing:content;
  height:auto !important; min-height:clamp(48px, 6vh, 72px) !important; max-height:40vh !important;
  overflow-y:auto !important; resize:none; color:#e5e5e5 !important;
}
.st-key-promptbox textarea::placeholder{
  color:#525252 !important; font-size:inherit !important; opacity:1;
}
.st-key-promptbox [data-testid="stForm"]{border:0; padding:0}
/* 隐藏原生「Press Ctrl+Enter to submit form」提示 */
.st-key-promptbox [data-testid="InputInstructions"]{display:none !important}
/* 发送键：40×40、圆角 8、蓝底白箭头（#root 级，压过全局按钮规则） */
/* Streamlit 给提交键包了一层 relative 的零尺寸容器，会把绝对定位甩到左上角，这里取消它 */
#root .st-key-promptbox .stElementContainer:has([data-testid="stFormSubmitButton"]),
#root .st-key-promptbox [class*="st-key-FormSubmitter"]{position:static !important}
/* bottom 取 10px：与预留区（59.75px）上下各留约 10px，视觉等距 */
.st-key-promptbox .stFormSubmitButton{
  display:block !important; position:absolute; right:0; bottom:10px; width:40px;
}
#root .st-key-promptbox [data-testid="stFormSubmitButton"] button{
  width:40px !important; height:40px !important; min-height:40px !important;
  padding:0 !important; border-radius:8px !important; border:0 !important;
  background:var(--accent) !important; color:#ffffff !important;
  font-size:18px !important; line-height:1; font-weight:600;
  box-shadow:none !important; transition:background .12s;
}
#root .st-key-promptbox [data-testid="stFormSubmitButton"] button p{
  font-size:18px !important; color:inherit !important; margin:0 !important; line-height:1 !important;
}
#root .st-key-promptbox [data-testid="stFormSubmitButton"] button:hover{
  background:var(--accent-hover) !important; color:#ffffff !important;
}


/* 附件上传入口改为整卡拖拽：组件保留在 DOM 中但不可见，仅用于接收拖入的文件 */
.st-key-cpattach{
  position:absolute !important; width:0 !important; height:0 !important;
  overflow:hidden !important; opacity:0 !important; pointer-events:none !important;
  left:0; bottom:0;
}
.st-key-cpattach [data-testid="stFileUploader"]{margin:0}

/* 快捷入口：卡片下方 40px，47 高，12 圆角，1px #404040 描边 */
.st-key-chips{margin-top:28px}
.st-key-chips [data-testid="stHorizontalBlock"]{
  gap:11px; row-gap:11px; justify-content:center; flex-wrap:wrap;
}
.st-key-chips [data-testid="stColumn"]{
  flex:0 0 auto !important; width:auto !important; min-width:0 !important;
}
.st-key-chips .stButton button{
  width:auto !important; height:47px !important; min-height:47px !important;
  padding:0 20px !important; border-radius:12px !important;
  display:inline-flex; align-items:center; justify-content:center; gap:8px;
  background:transparent !important; border:1px solid #404040 !important;
  color:#e5e5e5 !important; box-shadow:none !important;
  transition:background .12s, border-color .12s;
}
.st-key-chips .stButton button p{
  display:block !important; margin:0 !important;
  font-size:16px !important; line-height:1.5 !important; color:inherit !important;
}
.st-key-chips .stButton button [data-testid="stIconMaterial"]{
  font-size:16px !important; color:#a1a1a1 !important;
}
.st-key-chips .stButton button:hover{
  background:var(--hover-bg) !important; border-color:var(--line) !important; color:#fff !important;
}
.st-key-chips .stButton button:active{background:#242424 !important}











/* ---------- 卡片 ---------- */
.st-key-card-tasks, .st-key-card-files{
  background:var(--panel-3); border:1px solid var(--line); border-radius:8px;
  box-shadow:none; padding:12px 14px;
}
.st-key-card-tasks, .st-key-card-files{min-height:214px}
.fm-hr{height:1px;background:var(--line);margin:14px 0 10px}
.st-key-hero [data-testid="stFileUploaderDropzone"]{padding:6px 10px; min-height:38px}
.st-key-hero [data-testid="stFileUploaderDropzone"] button{padding:2px 8px; font-size:12px}
.st-key-hero [data-testid="stFileUploaderDropzone"] small{display:none}

/* ---------- Streamlit 控件 ---------- */
.stButton>button{
  border:1px solid var(--line-strong); background:var(--panel-3); color:var(--text);
  padding:4px 10px; border-radius:6px; font-weight:500; font-size:12px;
  box-shadow:none; transition:.12s;
}
.stButton>button:hover{border-color:#5a5a60; background:#303034; color:var(--text)}
.stButton>button:focus:not(:active){border-color:var(--accent-line); color:var(--text)}
.stButton>button[kind="primary"], [data-testid="stBaseButton-primary"]{
  background:var(--accent) !important; border-color:var(--accent) !important; color:#fff !important;
  box-shadow:none;
}
.stButton>button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover{background:var(--accent-hover) !important}

/* 设置页 · 外观切换：透明底，悬停深灰；选中项用强调色文字 + 细描边，不用色块 */
.st-key-theme_light button, .st-key-theme_dark button{
  background:transparent !important; border:1px solid transparent !important;
  box-shadow:none !important; color:var(--text-2) !important;
  min-height:34px; border-radius:8px; font-weight:500;
}
.st-key-theme_light button p, .st-key-theme_dark button p{
  color:inherit !important; font-size:12.5px; font-weight:inherit; margin:0;
}
.st-key-theme_light button:hover, .st-key-theme_dark button:hover{
  background:#1b1b1d !important; border-color:transparent !important; color:var(--text) !important;
}
.st-key-theme_light button[kind="primary"], .st-key-theme_dark button[kind="primary"]{
  background:transparent !important; border-color:var(--accent-line) !important;
  color:var(--accent) !important; font-weight:600;
}
.st-key-theme_light button[kind="primary"]:hover, .st-key-theme_dark button[kind="primary"]:hover{
  background:var(--accent-soft) !important; color:var(--accent) !important;
}



[data-testid="stFileUploader"] label{display:none}
[data-testid="stFileUploaderDropzone"]{
  background:var(--panel-3); border:1.5px dashed var(--line-strong); border-radius:6px;
  padding:10px 12px; min-height:0;
}
[data-testid="stFileUploaderDropzone"]:hover{border-color:var(--accent-line); background:var(--accent-soft)}
[data-testid="stFileUploaderDropzone"] small{color:var(--text-3); font-size:10.5px}
[data-testid="stFileUploaderDropzone"] span{font-size:12px}

[data-testid="stMultiSelect"] label{font-size:11.5px; color:var(--text-3)}
[data-testid="stExpander"] details{border:1px solid var(--line); border-radius:6px; background:var(--panel-3)}
[data-testid="stExpander"] summary{font-size:12px}
[data-testid="stVerticalBlock"]{gap:.55rem}

/* 对话输入条：单行胶囊（左「+」上传 / 中间输入 / 右语音图标 + 浅绿发送） */
.st-key-composer{
  position:relative;
  background:var(--panel-3); border:1px solid var(--line);
  border-radius:28px; box-shadow:0 1px 2px rgba(0,0,0,.04);
  padding:8px 10px 8px 8px;
  margin:4px 0 10px; width:100%; max-width:100%;
}
.st-key-cpchips{width:100%; max-width:100%}
/* 输入条固定在主内容区最下端（随侧栏展开/收起调整左边界） */
.st-key-composer{
  position:fixed !important; bottom:18px;
  left:calc(236px + 28px); right:28px; width:auto !important;
  max-width:none !important; margin:0 !important; z-index:900;
}
[data-testid="stAppViewContainer"]:has(.st-key-sbclosed) .st-key-composer{
  left:calc(52px + 28px);
}
.st-key-composer:focus-within{border-color:var(--line-strong); box-shadow:none}
.st-key-composer [data-testid="stForm"]{border:0; padding:0; margin:0 !important; background:transparent}
.st-key-composer [data-testid="stVerticalBlock"]{gap:0 !important}
.st-key-composer [data-testid="stElementContainer"]{margin:0 !important}
.st-key-composer [data-testid="stHorizontalBlock"]{align-items:center; gap:6px; flex-wrap:nowrap}
.st-key-composer [data-testid="stColumn"]{min-width:0}
.st-key-composer [data-testid="stTextArea"]>div,
.st-key-composer [data-testid="stTextArea"] div[data-baseweb="textarea"]{
  border:0 !important; background:transparent !important; box-shadow:none !important;
}
.st-key-composer textarea{
  border:0 !important; box-shadow:none !important; background:transparent !important;
  padding:10px 96px 10px 44px !important;
  font-size:15px !important; line-height:22px !important;
  min-height:44px !important; max-height:160px !important;
  color:var(--text) !important; resize:none; overflow-y:auto;
}
.st-key-composer textarea::placeholder{color:var(--text-3); font-size:15px; opacity:1}
/* 空态占位文字不换行，窄屏下省略而不是折行 */
.st-key-composer textarea:placeholder-shown{white-space:nowrap; overflow:hidden}
.st-key-composer [data-testid="InputInstructions"]{display:none !important}
/* 语音图标：用伪元素画在发送键左侧，不占布局 */
.st-key-composer::after{
  content:""; position:absolute; right:66px; top:50%; transform:translateY(-50%);
  width:20px; height:20px; pointer-events:none; opacity:.6;
  background:no-repeat center/20px 20px
    url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23a1a1a1' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><rect x='9' y='2.5' width='6' height='11' rx='3'/><path d='M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21'/></svg>");
}
/* 左侧「+」：隐藏的上传控件，叠加可点击的加号 */
.st-key-composer > [data-testid="stElementContainer"]:has(.st-key-cpattach2){
  position:absolute; inset:0; width:auto; height:auto; min-height:0; pointer-events:none;
}
.st-key-cpattach2{
  pointer-events:auto;
  position:absolute !important; left:10px; top:50%; transform:translateY(-50%);
  width:36px; height:36px; z-index:3;
}
.st-key-cpattach2 [data-testid="stFileUploader"]{margin:0}
.st-key-cpattach2 [data-testid="stFileUploaderDropzone"]{
  padding:0 !important; width:36px !important; height:36px !important; min-height:36px !important;
  border:0 !important; background:transparent !important; border-radius:10px !important;
  display:flex; align-items:center; justify-content:center; overflow:hidden;
}
.st-key-cpattach2 [data-testid="stFileUploaderDropzone"]:hover{background:rgba(0,0,0,.05) !important}
.st-key-cpattach2 [data-testid="stFileUploaderDropzoneInstructions"]{display:none !important}
.st-key-cpattach2 [data-testid="stFileUploaderDropzone"]::before{
  content:"+"; font-size:22px; font-weight:300; line-height:1; color:var(--text-2);
}
.st-key-cpattach2 [data-testid="stFileUploaderDropzone"] button{
  position:absolute !important; inset:0 !important;
  width:36px !important; height:36px !important; min-height:36px !important;
  padding:0 !important; border:0 !important; background:transparent !important;
  box-shadow:none !important; opacity:0 !important; cursor:pointer;
}
/* 发送键：44×44、浅绿底、深绿箭头（覆盖全局透明规则） */
#root .st-key-composer [data-testid="stFormSubmitButton"] button{
  width:44px !important; height:44px !important; min-height:44px !important;
  padding:0 !important; border:0 !important; border-radius:14px !important;
  background:#d9f7e6 !important; color:#0b7a44 !important;
  font-size:18px !important; line-height:1; font-weight:600; box-shadow:none !important;
  display:flex; align-items:center; justify-content:center;
}
#root .st-key-composer [data-testid="stFormSubmitButton"] button p{
  font-size:18px !important; color:inherit !important; margin:0 !important; line-height:1 !important;
}
#root .st-key-composer [data-testid="stFormSubmitButton"] button:hover{
  background:#c8f2db !important; color:#0b7a44 !important;
}



/* 环境条：卡片底部 55px 条（文件夹 / 本机），规范 4.4 */
.st-key-cpstore{
  /* 负边距在 flex 父级下不会自动加宽，这里显式撑满卡片内宽 + 两侧 padding */
  margin:0 -24px; padding:0 24px;
  width:calc(100% + 48px); max-width:calc(100% + 48px); box-sizing:border-box;
  min-height:55px; height:55px;
  background:#212121; border-top:1px solid #383838;
  border-radius:0 0 16px 16px;
  /* key 直接挂在 vertical block 上：这里本身当列容器用，内容垂直居中 */
  display:flex !important; flex-direction:column !important;
  justify-content:center !important; align-items:stretch !important;
}
.st-key-cpstore [data-testid="stVerticalBlock"]{gap:0 !important; margin:0 !important}
.st-key-cpstore > [data-testid="stVerticalBlock"]{
  height:55px !important; min-height:0 !important; max-height:55px;
  display:flex !important; flex-direction:column !important;
  justify-content:center !important; align-items:stretch !important;
}
.st-key-cpstore [data-testid="stHorizontalBlock"]{
  gap:10px; align-items:center; height:32px !important; min-height:0 !important;
  flex-wrap:nowrap !important; margin:0 !important;
}
/* 去掉列与按钮容器的默认外边距，保证上下等距 */
.st-key-cpstore [data-testid="stColumn"],
.st-key-cpstore [data-testid="stButton"],
.st-key-cpstore [data-testid="stVerticalBlock"] > div{margin:0 !important}
/* 两列按内容宽度排列，让「本机」紧挨「文件夹」 */
.st-key-cpstore [data-testid="stColumn"]{
  width:auto !important; flex:0 0 auto !important; min-width:0 !important;
}
.st-key-cpstore .stButton button,
.st-key-cpstore button{
  min-height:32px; height:32px; padding:0 6px; font-size:16px;
  border-radius:6px !important; box-shadow:none !important;
  background:transparent !important; border:0 !important;
  color:#e5e5e5 !important; justify-content:flex-start; overflow:hidden;
  transition:color .12s;
}
.st-key-cpstore .stButton button p,
.st-key-cpstore button p{
  font-size:16px; margin:0; white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; max-width:320px;
}
.st-key-cpstore button [data-testid="stIconMaterial"]{
  font-size:16px; color:#a1a1a1 !important; opacity:1;
}
.st-key-cpstore .stButton button:hover,
.st-key-cpstore button:hover{
  background:transparent !important; color:#ffffff !important;
}
/* 展开后的「本机 / 云端」小按钮：按内容收缩、略缩进 */
.st-key-cpstore .st-key-cp_store_local button,
.st-key-cpstore .st-key-cp_store_cloud button{
  width:auto !important; min-height:26px !important;
  padding:2px 12px !important; font-size:11.5px !important;
  margin-left:2px;
}
/* 「本机 / 云端」主按钮：悬停观感与首页图标完全一致（无边框、无阴影、浅灰底） */
.st-key-cpstore .st-key-cp_storage_btn button,
.st-key-cpstore .st-key-cp_model_btn button{
  border:0 !important; box-shadow:none !important;
  transition:background .15s ease, color .15s ease;
}
.st-key-cpstore .st-key-cp_storage_btn button:hover,
.st-key-cpstore .st-key-cp_model_btn button:hover{
  background:var(--hover-bg) !important;
  color:var(--text) !important;
  border:0 !important; box-shadow:none !important;
}
.st-key-cpstore .st-key-cp_storage_btn button:active,
.st-key-cpstore .st-key-cp_storage_btn button:focus,
.st-key-cpstore .st-key-cp_model_btn button:active,
.st-key-cpstore .st-key-cp_model_btn button:focus{
  background:transparent !important; border:0 !important; box-shadow:none !important;
}

/* 本机 / 云端 弹窗：浮于「本机」按钮正下方，不挤占布局 */
.st-key-cpstore [data-testid="stColumn"]:has(.st-key-cp_storage_btn),
.st-key-cpstore [data-testid="stColumn"]:has(.st-key-cp_model_btn){position:relative}
.st-key-cpstore, .st-key-herobox, .st-key-panel{overflow:visible !important}
.st-key-cp_store_menu, .st-key-cp_model_menu{
  position:absolute !important;
  right:0 !important; top:38px !important;
  z-index:1200;
  background:rgba(0,0,0,.7) !important;
  border:1px solid rgba(255,255,255,.14) !important;
  border-radius:12px; padding:8px 6px; margin:0 !important; width:136px;
  box-shadow:0 12px 30px rgba(0,0,0,.34), 0 2px 6px rgba(0,0,0,.22);
  gap:2px !important;
  backdrop-filter:blur(8px);
}
/* 两个弹窗都挂在各自按钮正下方：水平居中于按钮，上沿距按钮 6px */
#root .st-key-cpstore .st-key-cp_store_menu,
#root .st-key-cpstore .st-key-cp_model_menu{
  left:50% !important; right:auto !important;
  top:calc(100% + 6px) !important;
  transform:translateX(-50%);
}
/* 模型弹窗宽度锁定（Streamlit 自带 max-width:100% 会被父列夹窄） */
#root .st-key-cpstore .st-key-cp_model_menu{
  width:152px !important; min-width:152px !important; max-width:152px !important;
}
/* 模型弹窗内文字：默认 button p 是 16px 会把选项挤出按钮，这里压回 11.5px（本机弹窗保持原样） */
#root .st-key-cpstore .st-key-cp_model_menu button{height:26px !important; overflow:visible !important}
#root .st-key-cpstore .st-key-cp_model_menu button p{
  font-size:11.5px !important; max-width:none !important;
  white-space:nowrap !important; overflow:visible !important; text-overflow:clip !important;
}
#root .st-key-cpstore .st-key-cp_model_menu button [data-testid="stIconMaterial"]{font-size:14px !important}
/* 本机弹窗：同样锁定宽度，避免被父列（约 65px）夹窄导致「本机 / 云端」被截断 */
#root .st-key-cpstore .st-key-cp_store_menu{
  width:104px !important; min-width:104px !important; max-width:104px !important;
}
#root .st-key-cpstore .st-key-cp_store_menu button{overflow:visible !important}
#root .st-key-cpstore .st-key-cp_store_menu button p{
  max-width:none !important; white-space:nowrap !important;
  overflow:visible !important; text-overflow:clip !important;
}
#root .st-key-cp_store_menu button, #root .st-key-cp_model_menu button{border-radius:8px !important}
#root .st-key-cp_store_menu button, #root .st-key-cp_model_menu button{
  width:100% !important; min-height:26px !important; padding:2px 10px !important;
  background:transparent !important; border:0 !important; box-shadow:none !important;
  color:#f2f2f5 !important; font-size:11.5px !important;
}
#root .st-key-cp_store_menu button:hover, #root .st-key-cp_model_menu button:hover{
  background:rgba(255,255,255,.16) !important; color:#ffffff !important;
}
.st-key-cp_store_menu button p,
.st-key-cp_store_menu button [data-testid="stIconMaterial"],
.st-key-cp_model_menu button p,
.st-key-cp_model_menu button [data-testid="stIconMaterial"]{color:#f2f2f5 !important}
.cp-note{font-size:10.5px; color:var(--text-3); padding:4px 2px 0; line-height:1.5}
.cp-note.err{color:var(--err)}
.cp-note code{background:rgba(255,255,255,.1); padding:0 3px; border-radius:3px; font-size:10px}
[class*="st-key-cpchip_"] .stButton>button{
  border-radius:999px !important; border:1px solid var(--line-strong) !important;
  background:var(--panel-3) !important; color:var(--text-2) !important; font-size:11.5px;
  min-height:30px; box-shadow:none !important;
}
[class*="st-key-cpchip_"] .stButton>button:hover{border-color:var(--accent-line) !important; color:var(--accent) !important}
[data-testid="stBottomBlockContainer"]{background:var(--bg); max-width:1080px; padding:8px 24px 14px}
[data-testid="stBottom"]>div{background:transparent}
[data-testid="stMarkdownContainer"] p{font-size:12.5px}

/* ---------- 全站按钮：透明底 / 悬停深灰 / 点击后不留底色 ---------- */
/* 用 #root 提升优先级，压过 Streamlit 自带的 emotion hover 规则 */
#root .stButton>button,
#root .stButton>button[kind="primary"],
#root [data-testid^="stBaseButton"],
#root [data-testid="stFormSubmitButton"] button,
#root [data-testid="stDownloadButton"] button,
#root [class*="st-key-cpchip_"] .stButton>button{
  background:transparent !important; border-color:transparent !important;
  box-shadow:none !important; color:var(--text) !important;
  transition:background .12s ease, color .12s ease;
}
/* 需要主次区分的地方只靠文字色，不用色块 */
#root .st-key-sb-newproj .stButton>button,
#root .st-key-sb-newproj .stButton>button p,
#root .st-key-sb-newproj .stButton>button [data-testid="stIconMaterial"],
#root .st-key-nav .stButton>button[kind="primary"],
#root .st-key-nav .stButton>button[kind="primary"] p{
  background:transparent !important; border-color:transparent !important;
  color:var(--accent) !important;
}
#root .st-key-composer [data-testid="stFormSubmitButton"] button{
  background:transparent !important; border:0 !important; color:var(--accent) !important;
}
/* 焦点（点击后仍停留）：不留底色、不留描边 */
#root .stButton>button:focus, #root .stButton>button:focus:not(:active),
#root [data-testid^="stBaseButton"]:focus,
#root [data-testid="stFormSubmitButton"] button:focus,
#root [data-testid="stDownloadButton"] button:focus,
#root [class*="st-key-cpchip_"] .stButton>button:focus{
  background:transparent !important; border-color:transparent !important;
  box-shadow:none !important; color:var(--text) !important;
}
/* 悬停：全局用 --hover-bg token（侧栏有更具体的 [data-testid="stSidebar"] 覆盖规则在文末） */
.stButton>button:hover,
[data-testid^="stBaseButton"]:hover,
[data-testid="stFormSubmitButton"] button:hover,
[data-testid="stDownloadButton"] button:hover,
[class*="st-key-cpchip_"] .stButton>button:hover{
  background:var(--hover-bg) !important; color:var(--hover-text) !important;
  border-color:transparent !important; box-shadow:none !important;
}
#root .st-key-sb-newproj .stButton>button:hover,
#root .st-key-sb-newproj .stButton>button:hover p,
#root .st-key-composer [data-testid="stFormSubmitButton"] button:hover{color:var(--accent) !important}
/* 首页图标：悬停改为浅灰蒙层（暗色下用低透明度白，亮色下保持浅灰底） */
#root .st-key-chips .stButton button:hover{
  background:var(--hover-bg) !important; color:var(--text) !important;
}
/* 文件夹 / 存储：悬停同样用浅灰蒙层 */
#root .st-key-cpstore .stButton button:hover,
#root .st-key-cpstore button:hover{
  background:var(--hover-bg) !important; color:var(--text) !important;
}





/* ---------- 侧栏字号整体上调一档 ---------- */
section[data-testid="stSidebar"]{font-size:13.5px}
section[data-testid="stSidebar"] .fm-brand-name{font-size:15px}
section[data-testid="stSidebar"] .fm-brand-sub{font-size:11.5px}
section[data-testid="stSidebar"] .fm-mark{width:28px; height:28px; font-size:13px}
section[data-testid="stSidebar"] .fm-navlabel{font-size:11px; padding:10px 9px 4px}
section[data-testid="stSidebar"] .stButton>button{font-size:13.5px}
section[data-testid="stSidebar"] .stButton>button p{font-size:13.5px}
section[data-testid="stSidebar"] .stButton>button [data-testid="stIconMaterial"]{font-size:17px}
section[data-testid="stSidebar"] .st-key-sb-newproj .stButton>button p{font-size:13.5px}
section[data-testid="stSidebar"] .st-key-ws_toggle .stButton>button p,
section[data-testid="stSidebar"] .st-key-df_toggle .stButton>button p,
section[data-testid="stSidebar"] .st-key-pj_toggle .stButton>button p{font-size:12.5px; color:#8a8a93 !important}
section[data-testid="stSidebar"] .st-key-ws_toggle .stButton>button,
section[data-testid="stSidebar"] .st-key-df_toggle .stButton>button,
section[data-testid="stSidebar"] .st-key-pj_toggle .stButton>button{padding-left:0 !important; margin-left:0}
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p{font-size:12px}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary{font-size:13px}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary p{font-size:13px}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p{font-size:13px}

/* ---------- 统一悬停底色：所有可悬停元素一律浅灰 ---------- */
#root .stButton>button:hover,
#root .stButton button:hover,
#root .stDownloadButton>button:hover,
#root [data-testid^="stBaseButton"]:hover,
#root [data-testid="stFormSubmitButton"] button:hover,
#root [data-testid="stFileUploaderDropzone"]:hover,
#root [data-testid="stExpander"] summary:hover,
#root li[role="option"]:hover{
  background:var(--hover) !important;
}

/* ---------- 悬停提示卡片：浅灰底 + 深色文字 ---------- */
[data-baseweb="tooltip"],
[data-testid="stTooltipContent"],
[data-testid="stTooltipIcon"] [data-baseweb="tooltip"]{
  background:#ececf1 !important;
  color:#1f1f24 !important;
  border:1px solid #d8d8e0 !important;
  border-radius:6px !important;
  box-shadow:0 6px 16px rgba(0,0,0,.14) !important;
}
[data-baseweb="tooltip"] *,
[data-testid="stTooltipContent"] *{color:#1f1f24 !important; background-color:transparent !important}

/* ---------- 教学闭环：新增组件 ---------- */
/* 文件上传控件中文化，并提高文字对比度 */
[data-testid="stFileUploaderDropzoneInstructions"] span,
[data-testid="stFileUploaderDropzoneInstructions"] small{display:none !important}
[data-testid="stFileUploaderDropzoneInstructions"]::before{
  content:"拖拽文件到这里，或点击右侧「选择文件」"; color:var(--text-2);
  font-size:12.5px; font-weight:400; line-height:1.45; display:block}
[data-testid="stFileUploaderDropzoneInstructions"] div{display:block !important}
[data-testid="stFileUploaderDropzone"] button{font-size:0 !important}
[data-testid="stFileUploaderDropzone"] button::after{content:"选择文件"; font-size:12.5px}
[data-testid="stFileUploaderDropzone"] [data-testid="stMarkdownContainer"] p{
  color:var(--text-2) !important; font-size:12.5px}

/* 顶部课程上下文栏（全局唯一入口） */
.st-key-edu_ctxbar{
  border:1px solid var(--line); border-radius:8px; padding:4px 10px 6px;
  margin:0 0 12px; background:var(--panel-2);
}
.st-key-edu_ctxbar [data-baseweb="select"]>div{
  background:transparent !important; border-color:transparent !important; min-height:32px;
}
.st-key-edu_ctxbar [data-testid="stWidgetLabel"]{display:none}
.fm-stage{display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:11.5px;color:var(--text-3);min-height:32px}
.fm-stage b{color:var(--text);font-weight:550;font-size:12px}
.fm-stage .k{color:var(--text-3)}
.fm-stage .sep{width:1px;height:12px;background:var(--line);margin:0 2px}

/* 当前课程胶囊（非首页） */
.fm-coursepill{display:inline-flex;align-items:center;gap:7px;padding:4px 12px;
  border:1px solid var(--line);border-radius:999px;background:var(--panel);
  font-size:12px;color:var(--text-2);line-height:1.7;margin:0 0 12px}
.fm-coursepill .dt{width:6px;height:6px;border-radius:50%;background:var(--accent);flex:0 0 auto}
.fm-coursepill .lb{color:var(--text-3);font-size:11.5px}
.fm-coursepill b{color:var(--text);font-weight:600}

/* 统计卡 */
.fm-kpi{border:1px solid var(--line);border-radius:8px;background:var(--panel-3);
  padding:9px 12px;margin-bottom:8px;min-height:76px}
.fm-kpi .k{font-size:11px;color:var(--text-3)}
.fm-kpi .v{font-size:20px;font-weight:600;letter-spacing:-.4px;margin:2px 0;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fm-kpi .s{font-size:11px;color:var(--text-3)}
.fm-kpi.warn{border-color:rgba(204,167,0,.45)}
.fm-kpi.ok{border-color:rgba(137,209,133,.4)}

/* 课程上下文摘要 */
.fm-ctx{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:8px;
  border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin-bottom:10px;
  background:var(--panel-2)}
.fm-ctx .k{display:block;font-size:10.5px;color:var(--text-3);margin-bottom:2px}
.fm-ctx b{font-weight:550;font-size:12px}

/* 检查结果卡片 */
.fm-check{border:1px solid var(--line);border-left:3px solid var(--ok);border-radius:6px;
  background:var(--panel-3);padding:8px 10px;margin-bottom:8px}
.fm-check.warn{border-left-color:var(--warn)}
.fm-check .t{font-size:11.5px;font-weight:600}
.fm-check .d{font-size:11px;color:var(--text-3);margin-top:2px}

/* 对话气泡 */
.fm-msg{max-width:86%;margin:6px 0;padding:8px 11px;border-radius:10px;
  border:1px solid var(--line);background:var(--panel-3);font-size:12.5px;line-height:1.55;
  white-space:pre-wrap}
.fm-msg.ai{background:var(--accent-soft);border-color:var(--accent-line)}
.fm-msg .who{font-size:10.5px;color:var(--text-3);margin-bottom:2px}
.fm-msg.stu{margin-left:auto}

/* 记录表格 */
.fm-etable{width:100%;border-collapse:collapse;font-size:11.5px;margin:4px 0 10px}
.fm-etable th{text-align:left;color:var(--text-3);font-weight:500;
  border-bottom:1px solid var(--line);padding:5px 6px;white-space:nowrap}
.fm-etable td{border-bottom:1px solid var(--line);padding:5px 6px;
  vertical-align:top;word-break:break-word}
.fm-etable tr:hover td{background:var(--hover)}

/* 提示条 */
.fm-note{border:1px solid var(--accent-line);background:var(--accent-soft);border-radius:6px;
  padding:7px 10px;font-size:11.5px;margin:6px 0 10px}
.fm-note .muted{color:var(--text-3)}

/* 轻量 CSS 柱状图 */
.fm-bars{display:flex;flex-direction:column;gap:7px;margin:6px 0 12px}
.fm-bar{display:grid;grid-template-columns:150px 1fr 70px 90px;gap:8px;align-items:center;
  font-size:11.5px}
.fm-bar .lb{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-2)}
.fm-bar .tr{height:8px;background:var(--panel-3);border-radius:4px;overflow:hidden;
  border:1px solid var(--line)}
.fm-bar .fl{height:100%;background:var(--accent);border-radius:3px}
.fm-bar .vl{text-align:right;font-weight:600}
.fm-bar .nt{color:var(--text-3);font-size:10.5px}
@media (max-width:1400px){
  .fm-bar{grid-template-columns:110px 1fr 60px}
  .fm-bar .nt{display:none}
}

/* 按钮状态（hover / disabled / loading 由 Streamlit 提供） */
.stButton>button{transition:background .15s,border-color .15s,color .15s,filter .15s}
.stButton>button:disabled{opacity:.5;cursor:not-allowed}
.stButton>button[kind="primary"]{background:var(--accent);border-color:var(--accent);color:#fff}
.stButton>button[kind="primary"]:hover{filter:brightness(1.08)}
.fm-empty{border:1px dashed var(--line-strong);border-radius:8px;padding:14px;
  color:var(--text-3);font-size:12px;text-align:center;margin:6px 0 10px}

/* ==========================================================================
   SaaS 视觉规范（覆盖层）：暖米白 + 松绿 + 陶土橙 编辑部教育风格
   ========================================================================== */
:root{
  /* ==== 表面 ==== */
  --bg:#F5F1E8;
  --surface:#FFFCF6;
  --surface-elevated:#FFFFFF;
  --panel:#FFFCF6;
  --panel-2:#FFFFFF;
  --panel-3:#F9F5EC;
  /* ==== 边框 ==== */
  --line:#DED7C9;
  --line-strong:#CDBFA7;
  /* ==== 文字 ==== */
  --text:#25322D;
  --text-2:#66736C;
  --text-3:#94A199;
  /* ==== 品牌主色（松绿） ==== */
  --accent:#365B4C;
  --accent-hover:#426D5B;
  --accent-soft:rgba(54,91,76,.10);
  --accent-line:rgba(54,91,76,.35);
  /* ==== 品牌强调色（陶土橙） ==== */
  --brand-primary:#365B4C;
  --brand-accent:#B85C3E;
  --brand-accent-hover:#9D4B32;
  --brand-accent-soft:rgba(184,92,62,.12);
  --brand-accent-line:rgba(184,92,62,.35);
  /* ==== 语义 ==== */
  --ok:#3E7A5E;  --ok-soft:rgba(62,122,94,.12);
  --warn:#B8783E; --warn-soft:rgba(184,120,62,.12);
  --err:#B8443E;  --err-soft:rgba(184,68,62,.12);
  /* ==== 状态 ==== */
  --hover:#EEE8DB;
  --hover-bg:#EEE8DB;
  --hover-text:#2F5547;
  --active-bg:#DCE8E1;
  --active-text:#294D40;
  --focus-ring:rgba(184,92,62,.35);
  --caret-color:#B85C3E;
  /* ==== 圆角与阴影 ==== */
  --radius:14px;
  --radius-sm:10px;
  --shadow:0 1px 2px rgba(37,50,45,.04), 0 8px 24px rgba(37,50,45,.05);
  color-scheme:light;
}


html,body,.stApp,[data-testid="stAppViewContainer"]{
  background:var(--bg) !important; color:var(--text);
  font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
}
html,body,.stApp{font-size:14px; line-height:1.6; -webkit-font-smoothing:antialiased}
[data-testid="stMainBlockContainer"],.block-container{
  max-width:1280px !important; margin:0 auto !important;
  padding:20px 32px 96px !important;
}

/* ---------- 课程上下文栏 ---------- */
.st-key-edu_ctxbar{
  background:var(--panel); border:1px solid var(--line); border-radius:var(--radius);
  padding:10px 16px; margin-bottom:16px; box-shadow:var(--shadow);
}
.st-key-edu_ctxbar [data-testid="stHorizontalBlock"]{align-items:center; gap:12px}
.fm-coursebar{display:flex; align-items:center; gap:10px; min-width:0}
.fm-coursebar .lbl{font-size:12px; color:var(--text-2); white-space:nowrap}
.fm-rolebar{display:flex; justify-content:flex-end; align-items:center; gap:10px}
.fm-userchip{display:inline-flex; align-items:center; gap:8px; padding:5px 10px 5px 6px;
  border:1px solid var(--line); border-radius:999px; background:var(--panel); font-size:13px; color:var(--text)}
.fm-userchip .av{width:24px;height:24px;border-radius:50%;background:var(--accent-soft);
  color:var(--accent);display:grid;place-items:center;font-size:11px;font-weight:700}
.fm-userchip .nm{font-weight:600}
.fm-userchip .rl{color:var(--text-3); font-size:12px}

/* 分段切换（教师工作台 / 学生空间）—— Streamlit 1.50 选中态用 kind="segmented_controlActive" */
[data-testid="stButtonGroup"]{
  display:inline-flex !important; gap:2px; background:#F3F4F6 !important;
  border:1px solid var(--line) !important; border-radius:10px !important; padding:3px !important;
}
[data-testid="stButtonGroup"] button{
  border:0 !important; border-radius:8px !important; min-height:30px !important;
  padding:2px 14px !important; background:transparent !important; color:var(--text-2) !important;
  font-size:13px !important; font-weight:500 !important; box-shadow:none !important;
}
[data-testid="stButtonGroup"] button p{font-size:13px !important; margin:0}
/* 选中态：Streamlit 1.50 只用 kind / data-testid 标记，不设 aria-checked */
[data-testid="stButtonGroup"] button[kind*="segmented_controlActive"],
[data-testid="stButtonGroup"] [data-testid*="segmented_controlActive"]{
  background:var(--panel) !important; color:var(--accent) !important; font-weight:600 !important;
  box-shadow:0 1px 3px rgba(17,24,39,.12) !important;
}
[data-testid="stButtonGroup"] button[kind*="segmented_controlActive"] p,
[data-testid="stButtonGroup"] [data-testid*="segmented_controlActive"] p{color:var(--accent) !important}
.st-key-edu_ctxbar [data-baseweb="button-group"]{
  background:#F3F4F6 !important; border-radius:10px !important; padding:3px !important;
  border:1px solid var(--line) !important; gap:2px;
}
.st-key-edu_ctxbar [data-baseweb="button-group"] button{
  border:0 !important; border-radius:8px !important; min-height:30px !important;
  padding:2px 14px !important; background:transparent !important; color:var(--text-2) !important;
  font-size:13px !important; font-weight:500 !important; box-shadow:none !important;
}
.st-key-edu_ctxbar [data-baseweb="button-group"] button p{font-size:13px !important; margin:0}
.st-key-edu_ctxbar [data-baseweb="button-group"] button[kind*="segmented_controlActive"],
.st-key-edu_ctxbar [data-baseweb="button-group"] [data-testid*="segmented_controlActive"]{
  background:var(--panel) !important; color:var(--accent) !important; font-weight:600 !important;
  box-shadow:0 1px 3px rgba(17,24,39,.12) !important;
}

/* ---------- 侧边栏 ---------- */
section[data-testid="stSidebar"]{background:var(--panel) !important; border-right:1px solid var(--line)}
.fm-brand-name{font-size:15px; font-weight:700; color:var(--text)}
.fm-brand-sub{font-size:11px; color:var(--text-3)}
.fm-mark{background:var(--accent); border-radius:8px; width:28px; height:28px; font-size:13px}
.fm-navlabel{color:var(--text-3); font-size:11px; letter-spacing:.06em; padding:14px 10px 5px; font-weight:600}
.st-key-sbhead{border-bottom:1px solid var(--line); margin-bottom:10px; padding-bottom:10px}
.st-key-sbhead .stButton button:hover{background:var(--hover) !important; color:var(--text) !important}

.st-key-sb-newproj{margin:2px 0 6px}
.st-key-sb-newproj .stButton>button{
  min-height:42px !important; border-radius:10px !important;
  background:var(--accent) !important; border:1px solid var(--accent) !important;
  color:#fff !important; font-size:14px !important; font-weight:600 !important;
  justify-content:center !important; gap:6px !important;
  box-shadow:0 2px 6px var(--accent-soft) !important;
}
.st-key-sb-newproj .stButton>button p{font-size:14px !important; font-weight:600 !important; color:#fff !important}
.st-key-sb-newproj .stButton>button [data-testid="stIconMaterial"]{color:#fff !important}
.st-key-sb-newproj .stButton>button:hover{background:var(--hover-bg) !important; border-color:var(--accent-line) !important; color:var(--hover-text) !important}
.st-key-sb-newproj .stButton>button:hover p,.st-key-sb-newproj .stButton>button:hover [data-testid="stIconMaterial"]{color:var(--hover-text) !important}

.st-key-nav .stButton>button{
  min-height:38px !important; border-radius:9px !important; padding:6px 10px !important;
  font-size:13.5px !important; font-weight:500 !important; color:var(--text-2) !important;
  border:1px solid transparent !important; background:transparent !important;
  position:relative;
}
.st-key-nav .stButton>button p{font-size:13.5px !important; font-weight:500 !important}
/* 注：hover 状态统一收口到文末 [data-testid="stSidebar"] button:hover 覆盖规则 */
.st-key-nav .stButton>button[kind="primary"]{
  background:var(--accent-soft) !important; border-color:transparent !important;
  color:var(--accent) !important; font-weight:600 !important;
  border-left:3px solid var(--accent) !important; padding-left:9px !important;
}
.st-key-nav .stButton>button[kind="primary"] p{color:var(--accent) !important; font-weight:600 !important}
/* 注：primary hover 由文末 [data-testid="stSidebar"] button:hover 统一覆盖 */
.fm-sidefoot{border-top:1px solid var(--line); color:var(--text-2)}
.fm-av{background:var(--accent-soft); color:var(--accent)}

/* ---------- 卡片 / 面板 ---------- */
.st-key-panel,.st-key-panel-appearance,.st-key-panel-modelcfg,
.st-key-panel-setinfo,.st-key-panel-recent-tasks{
  background:var(--panel) !important; border:1px solid var(--line) !important;
  border-radius:var(--radius) !important; padding:20px 22px !important;
  box-shadow:var(--shadow); margin-bottom:16px;
}
.fm-cardhead h2{font-size:17px; font-weight:650; letter-spacing:-.2px}
.fm-cardhead .r{font-size:12px; color:var(--text-2)}
.fm-sec-title{font-size:14px; font-weight:650; margin:16px 0 8px; color:var(--text)}
.fm-hr{border-top:1px solid var(--line); margin:14px 0}

/* ---------- 按钮 ---------- */
.stButton>button,.stDownloadButton>button,.stFormSubmitButton>button{
  min-height:40px; border-radius:10px !important; font-size:14px; font-weight:500;
  border:1px solid var(--line) !important; background:var(--panel) !important; color:var(--text) !important;
  transition:background .15s,border-color .15s,color .15s,box-shadow .15s;
}
.stButton>button p,.stDownloadButton>button p,.stFormSubmitButton>button p{
  font-size:14px; font-weight:500; margin:0;
}
.stButton>button:hover,.stDownloadButton>button:hover,.stFormSubmitButton>button:hover{
  background:var(--hover-bg) !important; border-color:var(--accent-line) !important;
  color:var(--hover-text) !important;
}
.stButton>button:focus,
.stButton>button:focus-visible,
.stDownloadButton>button:focus,
.stDownloadButton>button:focus-visible,
.stFormSubmitButton>button:focus,
.stFormSubmitButton>button:focus-visible{
  box-shadow:0 0 0 3px var(--focus-ring) !important; outline:none !important;
}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"]{
  background:var(--accent) !important; border-color:var(--accent) !important; color:#fff !important;
  box-shadow:0 2px 6px var(--accent-soft);
}
.stButton>button[kind="primary"] p,.stFormSubmitButton>button[kind="primary"] p{color:#fff !important}
.stButton>button[kind="primary"]:hover,.stFormSubmitButton>button[kind="primary"]:hover{
  background:var(--hover-bg) !important; border-color:var(--accent-line) !important;
  color:var(--hover-text) !important;
}
.stButton>button[kind="primary"]:hover p,.stFormSubmitButton>button[kind="primary"]:hover p{color:var(--hover-text) !important}
.stButton>button:disabled,.stFormSubmitButton>button:disabled{
  background:#E5E7EB !important; border-color:#E5E7EB !important;
  color:#9CA3AF !important; box-shadow:none !important; opacity:1 !important;
}
.stButton>button:disabled p{color:#9CA3AF !important}

/* ---------- 输入框 ---------- */
[data-baseweb="input"],[data-baseweb="base-input"],[data-baseweb="textarea"],[data-baseweb="select"]>div{
  border-radius:10px !important; background:var(--panel) !important; border-color:var(--line) !important;
}
[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea{
  border-radius:10px !important; font-size:14px !important; color:var(--text) !important;
  min-height:40px;
}
[data-baseweb="input"]:focus-within,[data-baseweb="textarea"]:focus-within,
[data-baseweb="select"]>div:focus-within{
  border-color:var(--accent) !important; box-shadow:0 0 0 3px var(--focus-ring) !important;
  outline:none !important;
}
[data-testid="stWidgetLabel"] p{font-size:13px !important; font-weight:500; color:var(--text-2)}
[data-testid="stCaptionContainer"] p{color:var(--text-2) !important; font-size:12.5px}

/* ---------- 表格 ---------- */
.fm-etable{
  width:100%; border-collapse:separate; border-spacing:0; font-size:13px;
  border:1px solid var(--line); border-radius:12px; overflow:hidden; background:var(--panel);
}
.fm-etable th{
  background:var(--panel-3) !important; color:var(--text-2) !important; font-weight:600;
  font-size:12px; padding:10px 12px; border-bottom:1px solid var(--line);
}
.fm-etable td{padding:10px 12px; border-bottom:1px solid var(--line); font-size:13px}
.fm-etable tr:last-child td{border-bottom:0}
.fm-etable tr:hover td{background:#F8FAFF}
[data-testid="stHtml"]{max-width:100%; overflow-x:auto}

/* ---------- 标签 / 空状态 ---------- */
.fm-tag{font-size:12px; padding:2px 8px; border-radius:999px; background:#F3F4F6;
  border:1px solid var(--line); color:var(--text-2)}
.fm-empty{
  background:var(--panel); border:1px dashed var(--line-strong); border-radius:var(--radius);
  padding:30px 24px; color:var(--text-2); font-size:14px; text-align:center; margin:8px 0 12px;
}
.fm-list-item{padding:10px 2px}
.fm-li-t{font-size:14px; font-weight:550}
.fm-li-s{font-size:12px; color:var(--text-2)}

/* ---------- 首页 ---------- */
.st-key-herowrap{min-height:auto !important; padding:8px 0 8px; align-items:stretch !important}
.st-key-herowrap > [data-testid="stVerticalBlock"]{align-items:stretch !important}
.st-key-hero{max-width:960px !important; margin:0 auto}
.fm-h1{
  font-size:38px !important; line-height:1.25 !important; color:var(--text) !important;
  font-weight:700 !important; letter-spacing:-.8px; white-space:normal !important;
  text-align:center; margin:8px 0 10px !important;
}
.fm-hero-sub{text-align:center; color:var(--text-2); font-size:15px; margin:0 0 24px}
.st-key-herobox{
  background:var(--panel) !important; border:1px solid var(--line) !important;
  border-radius:16px !important; box-shadow:var(--shadow); padding:14px 16px 0 !important;
}
.st-key-herobox:focus-within{border-color:var(--accent) !important;
  box-shadow:0 0 0 3px var(--accent-soft) !important}
.st-key-promptbox [data-testid="stTextArea"] textarea{font-size:15px; min-height:52px; border:0 !important}
.st-key-promptbox [data-testid="stTextArea"] textarea:focus{box-shadow:none !important}
.st-key-chips [data-testid="stHorizontalBlock"]{gap:16px !important; flex-wrap:wrap}
.st-key-chips [data-testid="stColumn"]{min-width:220px; flex:1 1 220px}
[class*="st-key-qcard_"]{position:relative; margin-bottom:2px; transition:transform .2s ease}
.fm-qcard{
  background:var(--panel); border:1px solid var(--line); border-radius:var(--radius);
  padding:16px 18px; min-height:108px;
  transition:border-color .2s ease, box-shadow .2s ease, transform .2s ease, background .2s ease;
}
.fm-qcard .ic{width:34px;height:34px;border-radius:10px;background:var(--accent-soft);
  color:var(--accent);display:grid;place-items:center;margin-bottom:10px;font-size:17px;
  transition:background .2s ease, color .2s ease}
.fm-qcard .ic .fm-mi{
  font-family:"Material Symbols Rounded","Material Icons",sans-serif;
  font-size:20px; line-height:1; font-weight:400; letter-spacing:0;
  font-variation-settings:'FILL' 0,'wght' 400,'GRAD' 0,'opsz' 24;
  text-transform:none; white-space:nowrap; user-select:none;
}
.fm-qcard .tt{font-size:15px;font-weight:650;color:var(--text);margin-bottom:4px;
  transition:color .2s ease}
.fm-qcard .ds{font-size:12.5px;color:var(--text-2);line-height:1.55}
[class*="st-key-qcard_"] .stButton{position:absolute;inset:0;z-index:3;margin:0}
[class*="st-key-qcard_"] .stButton>button{
  width:100%; height:100%; min-height:100% !important; opacity:0; border:0 !important;
  background:transparent !important; box-shadow:none !important; cursor:pointer;
}
/* 悬浮效果：整卡上浮 + 浮动阴影 + 描边与图标强调 */
[class*="st-key-qcard_"]:hover{transform:translateY(-5px)}
[class*="st-key-qcard_"]:hover .fm-qcard{
  border-color:var(--accent);
  background:var(--panel);
  box-shadow:0 12px 32px rgba(47,85,71,.09), 0 2px 8px rgba(47,85,71,.05);
  transform:translateY(-1px);
}
[class*="st-key-qcard_"]:hover .fm-qcard .ic{background:var(--accent); color:#fff}
[class*="st-key-qcard_"]:hover .fm-qcard .tt{color:var(--accent)}
[class*="st-key-qcard_"]:active{transform:translateY(-2px)}

/* ---------- 指标卡 ---------- */
.fm-kpi{background:var(--panel);border:1px solid var(--line);border-radius:14px;
  padding:14px 16px;box-shadow:var(--shadow);height:100%}
.fm-kpi .k{font-size:12px;color:var(--text-2);margin-bottom:4px}
.fm-kpi .v{font-size:24px;font-weight:700;color:var(--text);line-height:1.25;letter-spacing:-.5px}
.fm-kpi .s{font-size:12px;color:var(--text-3);margin-top:4px}
.fm-kpi.ok .v{color:var(--ok)} .fm-kpi.warn .v{color:var(--warn)}

/* ---------- 其他教育组件 ---------- */
.fm-ctx,.fm-check,.fm-msg,.fm-note,.fm-stage,.fm-bars{
  background:var(--panel); border:1px solid var(--line); border-radius:12px;
}
.fm-ctx{padding:12px 16px; margin:0 0 14px}
.fm-stage{border:0;background:transparent;padding:0}
.fm-note{background:var(--accent-soft);border-color:var(--accent-line);color:var(--text);padding:10px 14px;font-size:13px}
.fm-msg{padding:10px 14px;margin:8px 0;background:#fff}
.fm-bar .tr{background:#EEF2F7;border:0;height:9px}
.fm-bar .fl{background:var(--accent)}
.fm-bar{font-size:12.5px;grid-template-columns:170px 1fr 64px 110px}
.fm-me .b{background:var(--accent-soft);border-color:var(--accent-line);color:var(--text)}

/* ---------- 展开面板 ---------- */
[data-testid="stExpander"] details{
  background:var(--panel) !important; border:1px solid var(--line) !important; border-radius:12px !important;
}
[data-testid="stExpander"] summary{padding:10px 14px !important; font-size:14px !important; color:var(--text) !important}
[data-testid="stExpander"] summary p{font-size:14px !important; font-weight:550; color:var(--text) !important}
section[data-testid="stSidebar"] [data-testid="stExpander"] details{background:var(--panel-3) !important}

/* ---------- 文件上传：中文文案 ---------- */
[data-testid="stFileUploaderDropzone"]{
  background:#FCFDFF !important; border:1.5px dashed var(--line-strong) !important;
  border-radius:12px !important; padding:14px !important;
}
[data-testid="stFileUploaderDropzone"]:hover{border-color:var(--accent) !important; background:#F8FAFF !important}
[data-testid="stFileUploaderDropzoneInstructions"] span,
[data-testid="stFileUploaderDropzoneInstructions"] small,
[data-testid="stFileUploaderDropzoneInstructions"] div{display:none !important}
[data-testid="stFileUploaderDropzoneInstructions"]::before{
  content:"将文件拖拽到此处"; display:block; font-size:13px; font-weight:600; color:var(--text); text-align:center;
}
[data-testid="stFileUploaderDropzoneInstructions"]::after{
  content:"或点击下方按钮选择本地文件"; display:block; font-size:12px; color:var(--text-2);
  text-align:center; margin-top:2px;
}
[data-testid="stFileUploader"] button,[data-testid="stFileUploaderDropzone"] button{
  border-radius:10px !important; font-size:13px !important; min-height:34px;
}
[data-testid="stFileUploader"] button p{font-size:13px !important}

/* ---------- 对话输入区 ---------- */
.st-key-composer{
  background:var(--panel) !important; border:1px solid var(--line) !important;
  border-radius:16px !important; padding:10px 12px 0 !important; box-shadow:var(--shadow);
}
.st-key-composer:focus-within{border-color:var(--accent) !important;
  box-shadow:0 0 0 3px var(--accent-soft) !important}
.st-key-composer [data-testid="stTextArea"] textarea{border:0 !important; font-size:14px}

/* ---------- AI 助手欢迎页 ---------- */
.fm-ai-hero{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:22px 24px;
  box-shadow:var(--shadow);margin-bottom:16px}
.fm-ai-hero h1{font-size:26px;margin:0 0 6px;font-weight:700;letter-spacing:-.5px}
.fm-ai-hero p{color:var(--text-2);margin:0;font-size:14px}
.fm-ai-meta{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}
.fm-ai-sugg{font-size:14px;font-weight:650;margin:18px 0 10px}
[class*="st-key-aicard_"]{position:relative}
[class*="st-key-aicard_"] .stButton{position:absolute;inset:0;z-index:3}
[class*="st-key-aicard_"] .stButton>button{width:100%;height:100%;opacity:0;border:0!important;background:transparent!important}
.fm-example{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px;
  font-size:13px;color:var(--text-2);min-height:64px;transition:border-color .15s,box-shadow .15s}
[class*="st-key-aicard_"]:hover .fm-example{border-color:var(--accent);box-shadow:0 4px 14px var(--accent-soft);color:var(--text)}

/* ---------- 空状态（无课程） ---------- */
.fm-crs-empty{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:36px 24px;
  text-align:center;box-shadow:var(--shadow);margin:8px 0 18px}
.fm-crs-empty .ic{width:52px;height:52px;border-radius:14px;background:var(--accent-soft);
  color:var(--accent);display:grid;place-items:center;margin:0 auto 14px;font-size:24px}
.fm-crs-empty h3{font-size:19px;margin:0 0 6px;font-weight:650}
.fm-crs-empty p{color:var(--text-2);font-size:14px;margin:0 auto 4px;max-width:520px}

/* ---------- 表单与页面通用 ---------- */
[data-testid="stForm"]{max-width:1000px}
[data-testid="stForm"] [data-testid="stFormSubmitButton"]{margin-top:6px}
.fm-cardhead{display:flex;align-items:baseline;justify-content:space-between;
  gap:12px;margin:0 0 8px}
.fm-sec-title{letter-spacing:-.1px}
[data-testid="stFileUploader"] section{padding:0}

/* ---------- 兼容旧结构 ---------- */
.st-key-promptbox textarea{
  color:var(--text) !important; min-height:46px !important; max-height:200px !important;
  font-size:15px !important; line-height:1.6 !important;
}
.st-key-promptbox textarea::placeholder{color:var(--text-3) !important}
.st-key-promptbox{border:0 !important; background:transparent !important; padding-bottom:46px !important}
#root .st-key-promptbox .stFormSubmitButton{width:auto !important}
#root .st-key-promptbox [data-testid="stFormSubmitButton"] button{
  width:auto !important; min-width:64px !important; padding:0 14px !important;
  border-radius:10px !important; font-size:13.5px !important; white-space:nowrap !important;
}
#root .st-key-promptbox [data-testid="stFormSubmitButton"] button p{
  font-size:13.5px !important; color:#fff !important; white-space:nowrap !important;
}
.st-key-chips [data-testid="stColumn"]{width:100% !important; flex:1 1 220px !important}
.st-key-chips [class*="st-key-qcard_"] .stButton>button{
  width:100% !important; height:100% !important; min-height:100% !important;
  padding:0 !important; border:0 !important; border-radius:0 !important;
  background:transparent !important; box-shadow:none !important;
}
#root .st-key-composer [data-testid="stFormSubmitButton"] button{
  background:var(--accent) !important; color:#fff !important;
  border-radius:10px !important; width:40px !important; height:40px !important;
  min-height:40px !important;
}
#root .st-key-composer [data-testid="stFormSubmitButton"] button p{color:#fff !important}
#root .st-key-composer [data-testid="stFormSubmitButton"] button:hover{background:var(--accent-hover) !important}
#root .st-key-composer [data-testid="stFormSubmitButton"] button:disabled{
  background:#E5E7EB !important; color:#9CA3AF !important;
}
#root .st-key-composer [data-testid="stFormSubmitButton"] button:disabled p{color:#9CA3AF !important}
.st-key-composer{border-radius:14px !important; padding:6px 10px !important;
  background:var(--panel) !important; border:1px solid var(--line) !important}
.st-key-composer textarea{padding:8px 10px !important; min-height:40px !important}
.st-key-composer::after{display:none !important}
.st-key-cpstore{
  background:#FCFDFF !important; border-top:1px solid var(--line) !important;
  border-radius:0 0 16px 16px !important;
  margin:0 -16px !important; padding:0 16px !important;
  width:calc(100% + 32px) !important; max-width:calc(100% + 32px) !important;
  min-height:46px !important; height:46px !important;
}
.st-key-cpstore .stButton button,.st-key-cpstore button{color:var(--text-2) !important}
.st-key-cpstore .stButton button p,.st-key-cpstore button p{font-size:13px !important}
.st-key-cpstore button [data-testid="stIconMaterial"]{color:var(--text-3) !important}
.st-key-cpstore .stButton button:hover,.st-key-cpstore button:hover{color:var(--accent) !important}
.st-key-cpstore > [data-testid="stVerticalBlock"]{height:46px !important; max-height:46px !important}

/* ---------- 深色主题（设置 → 外观）：带绿灰倾向的炭色 ---------- */
html:has(.fm-thememode.dark){
  --bg:#171C1A;
  --surface:#222925;
  --surface-elevated:#29312D;
  --panel:#222925;
  --panel-2:#29312D;
  --panel-3:#303A34;
  --line:#39433E;
  --line-strong:#4A554F;
  --text:#F2EEE5;
  --text-2:#AAB3AD;
  --text-3:#7D8A84;
  --accent:#A8C4B7;
  --accent-hover:#BCD5C9;
  --accent-soft:rgba(168,196,183,.14);
  --accent-line:rgba(168,196,183,.40);
  --brand-primary:#A8C4B7;
  --brand-accent:#E19A78;
  --brand-accent-hover:#EAB094;
  --brand-accent-soft:rgba(225,154,120,.14);
  --brand-accent-line:rgba(225,154,120,.40);
  --ok:#7FBEA1;   --ok-soft:rgba(127,190,161,.16);
  --warn:#E0A36C;  --warn-soft:rgba(224,163,108,.16);
  --err:#D87872;   --err-soft:rgba(216,120,114,.16);
  --hover:#2B3530;
  --hover-bg:#2B3530;
  --hover-text:#DCEADF;
  --active-bg:#34463D;
  --active-text:#C7E0D5;
  --focus-ring:rgba(225,154,120,.38);
  --caret-color:#E19A78;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.32);
  color-scheme:dark;
}

/* ----- 深色模式表面覆盖 ----- */
html:has(.fm-thememode.dark) section[data-testid="stSidebar"],
html:has(.fm-thememode.dark) .st-key-edu_ctxbar,
html:has(.fm-thememode.dark) .fm-userchip,
html:has(.fm-thememode.dark) .fm-qcard,
html:has(.fm-thememode.dark) .fm-note,
html:has(.fm-thememode.dark) .fm-kpi,
html:has(.fm-thememode.dark) .fm-ai-hero,
html:has(.fm-thememode.dark) .fm-example,
html:has(.fm-thememode.dark) .fm-crs-empty,
html:has(.fm-thememode.dark) .fm-empty,
html:has(.fm-thememode.dark) .fm-msg,
html:has(.fm-thememode.dark) .st-key-herobox,
html:has(.fm-thememode.dark) .st-key-composer,
html:has(.fm-thememode.dark) .st-key-cpstore,
html:has(.fm-thememode.dark) .st-key-cpattach,
html:has(.fm-thememode.dark) [data-testid="stExpander"] details{
  background:var(--panel) !important;
  border-color:var(--line) !important;
}
html:has(.fm-thememode.dark) [data-testid="stExpander"] summary{
  background:var(--panel) !important; color:var(--text) !important;
}
/* 深色：首页卡片悬浮阴影改用黑色投影，避免绿色光晕发脏 */
html:has(.fm-thememode.dark) [class*="st-key-qcard_"]:hover .fm-qcard{
  box-shadow:0 14px 32px rgba(0,0,0,.34), 0 2px 8px rgba(0,0,0,.22) !important;
}
/* 深色：按钮 hover 用松绿 tint，禁用用灰绿灰 */
html:has(.fm-thememode.dark) .stButton>button,
html:has(.fm-thememode.dark) .stDownloadButton>button,
html:has(.fm-thememode.dark) .stFormSubmitButton>button{
  background:var(--panel) !important; color:var(--text) !important; border-color:var(--line) !important;
}
html:has(.fm-thememode.dark) .stButton>button:hover,
html:has(.fm-thememode.dark) .stDownloadButton>button:hover,
html:has(.fm-thememode.dark) .stFormSubmitButton>button:hover{
  background:var(--hover-bg) !important; border-color:var(--accent-line) !important;
  color:var(--hover-text) !important;
}
html:has(.fm-thememode.dark) .stButton>button:disabled,
html:has(.fm-thememode.dark) .stFormSubmitButton>button:disabled{
  background:#2F3833 !important; border-color:#3E4943 !important; color:#7D8A84 !important;
}
html:has(.fm-thememode.dark) .stButton>button:disabled p{color:#7D8A84 !important}
/* 深色：主按钮（松绿底+深绿文字），hover 保持可对比 */
html:has(.fm-thememode.dark) .stButton>button[kind="primary"],
html:has(.fm-thememode.dark) .stFormSubmitButton>button[kind="primary"],
html:has(.fm-thememode.dark) .stButton>button[kind="primary"] p,
html:has(.fm-thememode.dark) .stFormSubmitButton>button[kind="primary"] p{
  color:#111A14 !important;
}
html:has(.fm-thememode.dark) .stButton>button[kind="primary"]:hover,
html:has(.fm-thememode.dark) .stFormSubmitButton>button[kind="primary"]:hover{
  background:var(--hover-bg) !important; border-color:var(--accent-line) !important;
  color:var(--hover-text) !important;
}
/* 深色：分段控件（选中态统一由文末「终极兜底」规则处理） */
html:has(.fm-thememode.dark) [data-testid="stButtonGroup"]{background:#2B3530 !important; border-color:var(--line) !important}
html:has(.fm-thememode.dark) [data-testid="stButtonGroup"] button{
  background:transparent !important; color:var(--text-2) !important;
}
/* 深色：输入/下拉不用纯黑 */
html:has(.fm-thememode.dark) [data-baseweb="input"],
html:has(.fm-thememode.dark) [data-baseweb="base-input"],
html:has(.fm-thememode.dark) [data-baseweb="textarea"],
html:has(.fm-thememode.dark) [data-baseweb="select"]>div{
  background:var(--panel-3) !important; border-color:var(--line) !important;
}
html:has(.fm-thememode.dark) [data-testid="stTextInput"] input,
html:has(.fm-thememode.dark) [data-testid="stNumberInput"] input,
html:has(.fm-thememode.dark) [data-testid="stTextArea"] textarea{
  color:var(--text) !important; background:transparent !important;
}
html:has(.fm-thememode.dark) [data-baseweb="popover"] [role="listbox"],
html:has(.fm-thememode.dark) [data-baseweb="popover"] ul,
html:has(.fm-thememode.dark) [data-baseweb="menu"]{
  background:var(--panel-2) !important;
}
html:has(.fm-thememode.dark) [data-baseweb="popover"] li,
html:has(.fm-thememode.dark) [data-baseweb="menu"] li{color:var(--text) !important}
html:has(.fm-thememode.dark) [data-baseweb="popover"] li:hover,
html:has(.fm-thememode.dark) [data-baseweb="menu"] li:hover{background:var(--hover-bg) !important}
html:has(.fm-thememode.dark) [data-testid="stFileUploader"] section,
html:has(.fm-thememode.dark) [data-testid="stFileUploader"] button{
  background:var(--panel-3) !important; border-color:var(--line) !important; color:var(--text-2) !important;
}
html:has(.fm-thememode.dark) [data-testid="stTabs"] button{color:var(--text-2) !important}
html:has(.fm-thememode.dark) [data-testid="stTabs"] button[aria-selected="true"]{color:var(--accent) !important}
html:has(.fm-thememode.dark) .fm-etable{background:var(--panel) !important}
html:has(.fm-thememode.dark) .fm-etable th{background:var(--panel-3) !important; color:var(--text-2) !important}
html:has(.fm-thememode.dark) .fm-etable td{color:var(--text) !important}
html:has(.fm-thememode.dark) .fm-etable tr:hover td{background:var(--hover-bg) !important}
html:has(.fm-thememode.dark) .fm-tag{background:var(--panel-3) !important; color:var(--text-2) !important}
html:has(.fm-thememode.dark) .st-key-cpstore{background:var(--panel-3) !important}

/* ----- 深色：侧边栏与导航不用半透明白/纯黑 ----- */
html:has(.fm-thememode.dark) [data-testid="stSidebar"] .stButton>button:hover{
  background:var(--hover-bg) !important; color:var(--hover-text) !important;
}
html:has(.fm-thememode.dark) .st-key-nav .stButton>button:hover{
  background:var(--hover-bg) !important; color:var(--hover-text) !important;
}
html:has(.fm-thememode.dark) .st-key-nav .stButton>button[kind="primary"]{
  background:var(--active-bg) !important; color:var(--active-text) !important;
  border-left-color:var(--accent) !important;
}
html:has(.fm-thememode.dark) .st-key-nav .stButton>button[kind="primary"]:hover{
  background:var(--hover-bg) !important; color:var(--hover-text) !important;
}
html:has(.fm-thememode.dark) .st-key-sb-newproj .stButton>button{
  background:var(--accent) !important; color:#111A14 !important; border-color:var(--accent) !important;
  box-shadow:0 2px 6px rgba(168,196,183,.22) !important;
}
html:has(.fm-thememode.dark) .st-key-sb-newproj .stButton>button:hover{
  background:var(--hover-bg) !important; border-color:var(--accent-line) !important;
  color:var(--hover-text) !important;
}

/* ---------- 响应式 ---------- */
@media (max-width:1280px){
  [data-testid="stMainBlockContainer"],.block-container{padding:16px 22px 90px !important}
  .fm-h1{font-size:32px !important}
  .fm-bar{grid-template-columns:120px 1fr 56px}
  .fm-bar .nt{display:none}
}
@media (max-width:1024px){
  .fm-h1{font-size:28px !important}
  .fm-qcard{min-height:96px; padding:14px}
}

/* ---------- 全局交互统一 ---------- */
*{outline:none !important;}
input,textarea,select,[contenteditable="true"]{
  caret-color:var(--caret-color);
}
button:focus, button:focus-visible,
a:focus, a:focus-visible,
input:focus, input:focus-visible,
textarea:focus, textarea:focus-visible,
select:focus, select:focus-visible{
  outline:none !important;
}

/* ========================================
   侧栏 hover / focus / active：全覆盖 Streamlit emotion hash class
   ======================================== */

/* 1) 侧栏整行容器 hover：让光标所在的整行（stElementContainer）变色 */
[data-testid="stSidebar"] .stElementContainer:hover,
[data-testid="stSidebar"] .stElementContainer:focus-within{
  background:var(--hover-bg) !important;
  border-radius:9px !important;
  margin-left:-6px !important; margin-right:-6px !important;
  padding-left:6px !important; padding-right:6px !important;
}
[data-testid="stSidebar"] .stElementContainer:hover [data-testid="stBaseButton"],
[data-testid="stSidebar"] .stElementContainer:hover .stButton > button{
  color:var(--hover-text) !important;
}
[data-testid="stSidebar"] .stElementContainer:hover [data-testid="stIconMaterial"]{
  color:var(--hover-text) !important;
}

/* 2) 侧栏按钮本体 hover / focus —— 覆盖 emotion hash class + Streamlit 默认 */
[data-testid="stSidebar"] button:hover,
[data-testid="stSidebar"] button:focus,
[data-testid="stSidebar"] button:focus-visible,
[data-testid="stSidebar"] [data-testid*="stBaseButton"]:hover,
[data-testid="stSidebar"] [data-testid*="stBaseButton"]:focus,
[data-testid="stSidebar"] [data-testid*="stBaseButton"]:focus-visible{
  background:var(--hover-bg) !important;
  color:var(--hover-text) !important;
  border-color:transparent !important;
  box-shadow:0 0 0 3px var(--focus-ring) !important;
}
/* 3) hover 时子元素（P/SPAN/图标/文字）颜色全部继承 —— 防止 emotion 单独设色 */
[data-testid="stSidebar"] button:hover *,
[data-testid="stSidebar"] [data-testid*="stBaseButton"]:hover *{
  color:inherit !important;
  background:transparent !important;
}

/* 4) 侧栏当前页由 .st-key-nav button[kind="primary"] 控制（见上方侧边栏段），此处不再重复 */

/* 5) 强制覆盖 Streamlit 默认深色 hover（rgb(48,48,52) 深灰近黑） */
.stButton > button:hover,
.stButton [data-testid*="stBaseButton"]:hover{
  background:var(--hover-bg) !important;
  color:var(--hover-text) !important;
  border-color:transparent !important;
}

/* 6) 分段控件 selected 统一收口到文末「终极兜底」规则 */

/* 7) 下拉菜单 option hover —— 禁止黑 */
[data-baseweb="popover"] li:hover, [data-baseweb="menu"] li:hover{
  background:var(--hover-bg) !important; color:var(--hover-text) !important;
}

/* 8) 表格行 hover */
.fm-etable tr:hover td{background:var(--hover-bg)}

/* 9) 标签选中态 */
.fm-tag.active, .fm-tag.ok{border-color:var(--accent-line); color:var(--accent)}

/* 10) 终极兜底：分段控件选中态（亮/暗）—— 必须用 #root 压过 Streamlit 框架的 !important */
#root button[kind="segmented_controlActive"],
#root [kind="segmented_controlActive"],
#root [data-testid*="segmented_controlActive"]{
  background:var(--panel) !important; color:var(--accent) !important;
  font-weight:600 !important;
}
#root button[kind="segmented_controlActive"] *,
#root [kind="segmented_controlActive"] *,
#root [data-testid*="segmented_controlActive"] *{
  color:var(--accent) !important;
}
/* 深色终极兜底 */
html:has(.fm-thememode.dark) #root button[kind="segmented_controlActive"],
html:has(.fm-thememode.dark) #root [kind="segmented_controlActive"],
html:has(.fm-thememode.dark) #root [data-testid*="segmented_controlActive"]{
  background:#1F2823 !important; color:var(--accent) !important; font-weight:600 !important;
  box-shadow:0 1px 2px rgba(0,0,0,.32) !important;
}
html:has(.fm-thememode.dark) #root button[kind="segmented_controlActive"] *,
html:has(.fm-thememode.dark) #root [kind="segmented_controlActive"] *,
html:has(.fm-thememode.dark) #root [data-testid*="segmented_controlActive"] *{
  color:var(--accent) !important;
}

</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
ss = st.session_state
ss.setdefault("nav", "首页")           # 当前视图
ss.setdefault("theme", "light")        # 外观：light / dark（设置页切换）
ss.setdefault("chat_history", [])      # [{role, text, steps?, error?}]
ss.setdefault("files", [])             # 本次会话已加载文件（历史文件见数据库）
ss.setdefault("docs", [])              # [{name, ext, chars, status, error?}] 智谱解析出的文档
ss.setdefault("required_cols", [])
ss.setdefault("gate_report", None)
ss.setdefault("load_errors", [])
ss.setdefault("task_route", None)     # 最近一次任务识别结果 {module,type,keywords,needs_data}
ss.setdefault("task_text", "")        # 最近一次任务原文
ss.setdefault("queued_prompt", None)  # 缺数据时暂存，上传成功后自动执行
ss.setdefault("auto_run", False)

def _visible_projects(projects: list[dict]) -> list[dict]:
    """界面展示的项目列表：不显示系统内置的「默认项目」。"""
    return [p for p in projects if p["name"] != "默认项目"]


# 当前项目：启动时定位到第一个可见项目（没有项目则为空）
def _ensure_current_project() -> tuple[Optional[int], str]:
    projects = db.list_projects()
    visible = _visible_projects(projects)
    if not visible:
        ss.current_project_id = None
        ss.current_project_name = ""
        return None, ""
    visible_pids = {p["id"] for p in visible}
    if ss.get("current_project_id") not in visible_pids:
        ss.current_project_id = visible[0]["id"]
    p = db.get_project(ss.current_project_id)
    ss.current_project_name = p["name"] if p else ""
    return int(ss.current_project_id), ss.current_project_name

ss.setdefault("current_project_id", None)
ss.setdefault("current_project_name", None)
ss.setdefault("edu_mode", "教师模式")   # 教师模式 / 学生模式
ss.setdefault("edu_student_name", "")

# 刷新页面后恢复课程与教师/学生模式（从 URL query 读回）
if not ss.get("_qp_restored"):
    ss._qp_restored = True
    try:
        _qp_course = st.query_params.get("course")
        _qp_mode = st.query_params.get("mode")
        _qp_theme = st.query_params.get("theme")
    except Exception:
        _qp_course, _qp_mode, _qp_theme = None, None, None
    if _qp_theme in ("light", "dark"):
        ss.theme = _qp_theme
    if _qp_course:
        try:
            _p = db.get_project(int(_qp_course))
            if _p:
                ss.current_project_id = int(_qp_course)
                ss.current_project_name = _p["name"]
        except (TypeError, ValueError):
            pass
    if _qp_mode == "student":
        ss.edu_mode = "学生模式"

if ss.get("pending_prompt") is not None:
    ss.prompt_text = ss.pop("pending_prompt")


def _esc(v) -> str:
    return html.escape(str(v if v is not None else ""))


def _path_html(v) -> str:
    """路径转义，并在路径分隔符后插入换行点，避免在词中间断开。"""
    s = _esc(v)
    return s.replace("\\", "\\<wbr>").replace("/", "/<wbr>")


def _fmt_time(ts) -> str:
    try:
        return time.strftime("%m-%d %H:%M", time.localtime(float(ts)))
    except Exception:
        return ""


def _human_size(n) -> str:
    try:
        n = float(n)
    except Exception:
        return "—"
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f} MB"
    if n >= 1 << 10:
        return f"{n / (1 << 10):.1f} KB"
    return f"{int(n)} B"


# ---------------------------------------------------------------------------
# 任务分发：识别 → 跳到对应界面 → 自动执行（缺数据则先排队）
# ---------------------------------------------------------------------------
_MODULE_HINT = {
    "教学工具": "表格 · 文档 · 演示，统一在此页完成",
    "AI 助手": "通用问答与文档解读",
}


def _has_data() -> bool:
    return bool(_REGISTRY.get("current") or get_documents())


def _requests_excel_output(text: str) -> bool:
    """识别允许直接从本轮文本建表并导出 Excel 的请求。"""
    t = (text or "").lower()
    has_output = any(w in t for w in ("excel", "xlsx", "表格", "工作簿"))
    has_action = any(w in t for w in ("生成", "制作", "创建", "导出", "保存为", "转成", "转换为", "整理成"))
    return has_output and has_action


def _dispatch_task(text: str) -> None:
    """首页提交入口：识别任务类型，跳转到对应界面并按需自动执行。"""
    text = (text or "").strip()
    if not text:
        return
    route = classify(text)
    ss.task_route = route
    ss.task_text = text
    ss.auto_run = False
    ss.queued_prompt = None
    if route["needs_data"] and not _has_data() and not _requests_excel_output(text):
        # 分析类任务缺少数据时先上传；文本建表任务可直接进入 Agent 执行
        ss.nav = "教学工具"
        ss.queued_prompt = text
    else:
        ss.nav = route["module"]
        ss.auto_run = True


def _task_banner(module: str) -> None:
    """在目标界面顶部展示识别结果（类型 / 原文 / 命中关键词）。"""
    route = ss.get("task_route")
    if not route or route.get("module") != module:
        return
    kws = "、".join(route.get("keywords") or []) or "无关键词，按通用任务处理"
    st.html(
        '<div class="fm-routebar">'
        f'<span class="fm-tag ok"><span class="fm-dot"></span>已识别 · {_esc(route["type"])}</span>'
        f'<div class="fm-route-b"><div class="fm-route-t">{_esc(ss.get("task_text", ""))}</div>'
        f'<div class="fm-route-s">命中：{_esc(kws)} · {_esc(_MODULE_HINT.get(module, ""))}</div></div>'
        '</div>'
    )


def _ic(path: str) -> str:
    return (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" '
        f'stroke-linejoin="round">{path}</svg>'
    )


def _safe_dirname(name: str) -> str:
    """把项目名转成合法的本地文件夹名。"""
    bad = '<>:"/\\|?*'
    s = "".join("_" if ch in bad else ch for ch in name).strip().strip(".")
    return s or "project"


def _project_folder(proj: dict | None) -> Path | None:
    """返回项目对应的本地文件夹（不存在则按需创建）。"""
    if not proj:
        return None
    folder = (proj.get("folder") or "").strip()
    p = Path(folder) if folder else (PROJECT_DIR / _safe_dirname(proj["name"]))
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None
    return p


def _open_in_explorer(folder: str) -> bool:
    """在本机文件管理器（资源管理器）中打开指定文件夹；成功返回 True。"""
    try:
        p = Path(folder)
        p.mkdir(parents=True, exist_ok=True)
        os.startfile(str(p))
        return True
    except Exception:
        return False


# 环境条弹窗（模型 / 本机）：光标移出弹窗与主按钮后自动收起（再点一次主按钮 = 关闭）
_MENU_HOVER_JS = """
<script>
(function(){
  var w = window.parent, d = w.document;
  var pairs = [
    ['.st-key-cp_model_menu', '.st-key-cp_model_btn'],
    ['.st-key-cp_store_menu', '.st-key-cp_storage_btn']
  ];
  if (typeof w.__zhiyiMenuHoverOff === 'function') { w.__zhiyiMenuHoverOff(); }
  var cleanup = [];
  function inside(node, target){ return !!(node && target && node.contains(target)); }
  pairs.forEach(function(pair){
    var menu = d.querySelector(pair[0]);
    var host = d.querySelector(pair[1]);
    if (!menu || !host) { return; }
    var btn = host.tagName === 'BUTTON' ? host : host.querySelector('button');
    if (!btn) { return; }
    var timer = null;
    function schedule(ev){
      if (ev && (inside(menu, ev.relatedTarget) || inside(btn, ev.relatedTarget))) { return; }
      clearTimeout(timer);
      timer = setTimeout(function(){
        if (!d.body.contains(menu)) { return; }
        if (menu.matches(':hover') || btn.matches(':hover')) { return; }
        btn.click();
      }, 160);
    }
    menu.addEventListener('mouseleave', schedule);
    btn.addEventListener('mouseleave', schedule);
    // 贴近视口右侧时把弹窗拉回可视区，避免被裁切
    var raf = w.requestAnimationFrame || function(fn){ return setTimeout(fn, 16); };
    raf(function(){
      var r = menu.getBoundingClientRect();
      var vw = d.documentElement.clientWidth, pad = 8, shift = 0;
      if (r.right > vw - pad) { shift = (vw - pad) - r.right; }
      if (r.left + shift < pad) { shift = pad - r.left; }
      if (shift) { menu.style.transform = 'translateX(calc(-50% + ' + shift + 'px))'; }
    });
    cleanup.push(function(){
      clearTimeout(timer);
      menu.removeEventListener('mouseleave', schedule);
      btn.removeEventListener('mouseleave', schedule);
    });
  });
  w.__zhiyiMenuHoverOff = function(){ cleanup.forEach(function(fn){ fn(); }); };
}());
</script>
"""


def _render_storage_row(proj: dict | None) -> None:
    """输入框下方工具行：任务保存文件夹 + 任务存储位置（均为按钮）。"""
    if ss.get("cp_folder_pid") != ss.get("current_project_id"):
        ss.cp_folder_pid = ss.get("current_project_id")
        # 没有项目时回退到项目输出目录，保证「文件夹」按钮随时能打开资源管理器
        ss["cp_folder"] = str(_project_folder(proj) or PROJECT_DIR)

    def _on_open_folder() -> None:
        folder = (ss.get("cp_folder") or "").strip() or str(PROJECT_DIR)
        if not _open_in_explorer(folder):
            ss["cp_folder_msg"] = "无法打开文件管理器，请检查该路径是否可访问"
            return
        ss["cp_folder_msg"] = ""

    def _toggle_store_panel() -> None:
        ss["cp_store_open"] = not ss.get("cp_store_open", False)

    def _pick_store(target: str) -> None:
        ss["cp_storage"] = target
        ss["cp_store_open"] = False

    def _toggle_model_panel() -> None:
        ss["cp_model_open"] = not ss.get("cp_model_open", False)

    def _pick_model(name: str) -> None:
        ss["cp_model_open"] = False
        if _apply_model_provider(name):
            ss.model_provider = name
            ss.cfg_provider = name  # 让「设置 → 模型配置」的下拉同步
            return
        ss["cp_folder_msg"] = f"{name} 未配置密钥，请到「设置 → 模型配置」填写。"

    _folder = (ss.get("cp_folder") or "").strip() or str(PROJECT_DIR)
    _folder_label = f"课程资料 · {Path(_folder).name or _folder}"
    _storage = ss.get("cp_storage") or "本机数据库"

    with st.container(key="cpstore"):
        _fa, _fb, _fm = st.columns([2.3, 1.0, 1.2])
        with _fa:
            st.button(_folder_label, key="cp_folder_btn", on_click=_on_open_folder,
                      icon=":material/folder:", help=f"点击在文件管理器中打开 {_folder or '当前目录'}",
                      use_container_width=True)
        with _fb:
            st.button("本地文件" if _storage == "本机数据库" else "云端存储",
                      key="cp_storage_btn", on_click=_toggle_store_panel,
                      icon=":material/folder_open:", help="点击展开选择本地 / 云端存储",
                      use_container_width=True)
            if ss.get("cp_store_open"):
                with st.container(key="cp_store_menu"):
                    st.button("本地文件", key="cp_store_local", on_click=_pick_store,
                              args=("本机数据库",), icon=":material/computer:",
                              use_container_width=True)
                    st.button("云端存储", key="cp_store_cloud", on_click=_pick_store,
                              args=("云端数据库",), icon=":material/cloud:",
                              use_container_width=True)
        with _fm:
            st.button(ss.get("model_provider", "DeepSeek"), key="cp_model_btn",
                      on_click=_toggle_model_panel, icon=":material/swap_horiz:",
                      help="点击展开选择对话模型", use_container_width=True)
            if ss.get("cp_model_open"):
                with st.container(key="cp_model_menu"):
                    st.button("DeepSeek", key="cp_model_deepseek", on_click=_pick_model,
                              args=("DeepSeek",), icon=":material/memory:",
                              use_container_width=True)
                    st.button("智谱 GLM", key="cp_model_zhipu", on_click=_pick_model,
                              args=("智谱 GLM",), icon=":material/auto_awesome:",
                              use_container_width=True)
        # 任一弹窗展开时挂上「移出自动关闭」脚本
        if ss.get("cp_model_open") or ss.get("cp_store_open"):
            components.html(_MENU_HOVER_JS, height=0)
    if ss.get("cp_folder_msg"):
        st.html(f'<div class="cp-note">{_esc(ss.cp_folder_msg)}</div>')
    if _storage == "云端数据库":
        st.html('<div class="cp-note">云端数据库尚未配置，本次任务仍写入本机数据库 '
                '<code>.data/workbench.db</code>；配置连接串后才会切换到云端。</div>')


# ---------------------------------------------------------------------------
# 侧边栏：品牌 / 导航 / 上下文 / 模型配置
# ---------------------------------------------------------------------------
_TEACHER_VIEWS = {"课程项目", "一键备课", "创建实训", "作业评审", "学情分析",
                  "教学工具", "AI 助手", "教学素材", "文件", "任务", "设置"}


# 对话模型切换：两个 OpenAI 兼容端点，切换后写入 LLM_* 环境变量，下一次对话生效
_MODEL_PROVIDERS = {
    "DeepSeek": ("https://api.deepseek.com/v1", "deepseek-chat", LLM_API_KEY),
    "智谱 GLM": (ZHIPU_BASE_URL, ZHIPU_MODEL, ZHIPU_API_KEY),
}


def _apply_model_provider(name: str) -> bool:
    """把指定服务商的地址/模型/密钥写入环境变量；密钥缺失时返回 False。"""
    url, model, key = _MODEL_PROVIDERS[name]
    if not key or key.startswith("sk-REPLACE"):
        return False
    os.environ["LLM_BASE_URL"] = url
    os.environ["LLM_MODEL"] = model
    os.environ["LLM_API_KEY"] = key
    return True


with st.sidebar:
    # 品牌区 + 收起/展开开关同一行；开关在导航栏内部
    _sb_open = ss.get("sidebar_open", True)
    with st.container(key="sbhead"):
        _hb1, _hb2 = st.columns([1, 0.13], gap="small", vertical_alignment="center")
        with _hb1:
            st.html(
                '<div class="fm-brand"><div class="fm-mark">致</div><div>'
                '<div class="fm-brand-name">致壹</div>'
                '<div class="fm-brand-sub">智能教育 · 本地运行</div></div></div>'
            )
        with _hb2:
            if st.button(
                "\u200b",
                key="sbtoggle_btn",
                icon=":material/chevron_left:" if _sb_open else ":material/chevron_right:",
            ):
                ss.sidebar_open = not _sb_open
                st.rerun()

    # ---- 新建教学任务（侧栏顶部主按钮） ----
    with st.container(key="sb-newproj"):
        if st.button("＋ 新建教学任务", key="sb_newtask", use_container_width=True):
            ss.prompt_text = ""
            ss.task_route = None
            ss.task_text = ""
            ss.queued_prompt = None
            ss.auto_run = False
            ss.nav = "首页"
            st.rerun()

    _is_stu = edu_ui.is_student_mode()
    if _is_stu:
        _groups = [("学习", [
            ("学生首页", "首页", ":material/home:"),
            ("我的任务", "我的任务", ":material/assignment:"),
            ("我的答疑", "学生答疑", ":material/forum:"),
            ("教师反馈", "教师反馈", ":material/rate_review:"),
            ("错题回顾", "错题回顾", ":material/history_edu:"),
        ])]
    else:
        _groups = [
            ("教学流程", [
                ("课程项目", "课程项目", ":material/folder_open:"),
                ("一键备课", "一键备课", ":material/menu_book:"),
                ("创建实训", "创建实训", ":material/build:"),
                ("学生答疑", "学生答疑", ":material/question_answer:"),
                ("作业评审", "作业评审", ":material/fact_check:"),
                ("学情分析", "学情分析", ":material/insights:"),
            ]),
            ("工具", [
                ("AI 助手", "AI 助手", ":material/smart_toy:"),
                ("教学工具", "教学工具", ":material/handyman:"),
                ("教学素材", "教学素材", ":material/image_search:"),
            ]),
            ("系统", [
                ("文件", "文件", ":material/folder:"),
                ("任务", "任务", ":material/task_alt:"),
                ("设置", "设置", ":material/settings:"),
            ]),
        ]

    with st.container(key="nav"):
        for _label, _items in _groups:
            st.html(f'<div class="fm-navlabel">{_esc(_label)}</div>')
            for _name, _target, _icon in _items:
                if st.button(
                    _name,
                    key=f"navbtn_{_target}",
                    icon=_icon,
                    use_container_width=True,
                    type="primary" if ss.get("nav") == _target else "secondary",
                ):
                    ss.nav = _target
                    st.rerun()

    _foot_name = (ss.get("edu_student_name") or "学生A") if _is_stu else "本地用户"
    _foot_role = "学生空间" if _is_stu else "教师 · 单租户"
    st.html(
        f'<div class="fm-sidefoot"><div class="fm-av">{"学" if _is_stu else "师"}</div>'
        f'<div style="min-width:0"><div class="fm-li-t" style="font-size:13px">{_esc(_foot_name)}</div>'
        f'<div class="fm-li-s">{_esc(_foot_role)}</div></div></div>'
    )


def _switch_course(pid: int, name: str) -> None:
    """切换课程：同步 query 参数，并清掉上节课的临时结果，避免串课程。"""
    ss.current_project_id = int(pid)
    ss.current_project_name = name
    ss["last_course_id"] = int(pid)
    ss["last_course_name"] = name
    st.query_params["course"] = str(int(pid))
    for k in ("edu_lesson_pkg", "edu_lesson_meta", "edu_lesson_task_id", "edu_lesson_prefill",
              "edu_review", "edu_review_meta", "edu_review_accept", "edu_next_plan",
              "edu_next_path", "edu_tutor", "edu_training_pkg", "edu_training_task_id",
              "edu_review_task_id"):
        ss.pop(k, None)
    st.rerun()


def _course_bar_controls(projects: list[dict]) -> None:
    """课程选择 / 创建课程 / 模式切换 / 当前用户。"""
    c1, c2, c3, c4 = st.columns([3.1, 1.35, 2.3, 1.55], vertical_alignment="center")
    with c1:
        labels = ["（未选择课程）"] + [p["name"] for p in projects]
        cur = ss.get("current_project_name")
        sel = st.selectbox("课程", labels,
                           index=labels.index(cur) if cur in labels else 0,
                           key="top_course_sel", label_visibility="collapsed")
        if sel != "（未选择课程）" and sel != cur:
            pid = next(p["id"] for p in projects if p["name"] == sel)
            _switch_course(pid, sel)
    with c2:
        if st.button("＋ 创建课程", key="top_new_course", use_container_width=True):
            ss["edu_open_new"] = True
            ss.nav = "课程项目"
            st.rerun()
    with c3:
        mode = st.segmented_control(
            "使用模式", ["教师工作台", "学生空间"],
            default="学生空间" if edu_ui.is_student_mode() else "教师工作台",
            key="edu_mode_seg", label_visibility="collapsed")
        want = "学生模式" if mode == "学生空间" else "教师模式"
        if mode and want != ss.get("edu_mode", "教师模式"):
            ss.edu_mode = want
            st.query_params["mode"] = "student" if want == "学生模式" else "teacher"
            ss.nav = "首页"
            st.rerun()
    with c4:
        if edu_ui.is_student_mode():
            name = st.text_input("学生身份", value=ss.get("edu_student_name") or "",
                                 key="edu_student_top", label_visibility="collapsed",
                                 placeholder="学生身份：学生A")
            ss.edu_student_name = (name or "").strip()
        else:
            st.html(
                '<div class="fm-rolebar"><div class="fm-userchip">'
                '<div class="av">师</div><span class="nm">教师</span>'
                '<span class="rl">本地账号</span></div></div>'
            )


def _render_course_bar() -> None:
    """课程上下文：首页常驻完整入口，其余页面只显示当前课程胶囊。"""
    projects = _visible_projects(db.list_projects())
    proj = db.get_project(ss["current_project_id"]) if ss.get("current_project_id") else None
    if VIEW == "首页":
        with st.container(key="edu_ctxbar"):
            _course_bar_controls(projects)
    else:
        # 非首页只保留一枚提示当前课程的胶囊，切换课程回首页
        st.html(
            '<div class="fm-coursepill"><span class="dt"></span>'
            f'<span class="lb">当前课程</span><b>{_esc(proj["name"] if proj else "未选择课程")}</b></div>'
        )
    if proj:
        ss["last_course_id"] = proj["id"]
        ss["last_course_name"] = proj["name"]
    # 首次进入也写入 query，保证刷新后仍停留在同一课程
    if proj and not st.query_params.get("course"):
        try:
            st.query_params["course"] = str(proj["id"])
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 顶栏
# ---------------------------------------------------------------------------
VIEW = ss.get("nav", "首页")
# 兼容旧会话：四个工作台已合并为「教学工具」，旧名称一并迁移
if VIEW in ("默认工作台", "Excel 工作台", "Word 工作台", "PPT 工作台", "数据分析", "报告工坊", "办公软件"):
    VIEW = ss.nav = "教学工具"


# 全局课程上下文：唯一的课程切换入口 + 教师/学生模式切换
_ensure_current_project()
_render_course_bar()

# 侧栏收起状态标记：供 CSS :has() 识别（开关按钮在侧栏内）
if not ss.get("sidebar_open", True):
    with st.container(key="sbclosed"):
        st.html('<span></span>')


# ---------------------------------------------------------------------------
# 视图：首页 Hero（含数据源）
# ---------------------------------------------------------------------------
def render_hero() -> None:
    """首页：教学任务入口页（教师）/ 学习入口页（学生）。"""
    _stu = edu_ui.is_student_mode()
    proj = db.get_project(ss["current_project_id"]) if ss.get("current_project_id") else None

    with st.container(key="herowrap"):
        with st.container(key="hero"):
            if _stu:
                st.html('<h1 class="fm-h1">今天想解决什么问题？</h1>')
                st.html('<p class="fm-hero-sub">可以上传题目图片，也可以直接描述你不理解的地方。</p>')
            else:
                st.html('<h1 class="fm-h1">今天要完成哪项教学任务？</h1>')
                st.html('<p class="fm-hero-sub">从备课到答疑、实训和评价，统一在同一门课程中完成。</p>')

            with st.container(key="herobox"):
                with st.container(key="promptbox"):
                    with st.form("prompt_form", border=False, enter_to_submit=True,
                                 clear_on_submit=False):
                        st.text_area(
                            "教学需求",
                            key="prompt_text",
                            height=44,
                            placeholder=("粘贴题目、描述问题或上传题目图片。"
                                         if _stu else
                                         "输入课题、上传资料，或描述你要完成的教学任务。"),
                            label_visibility="collapsed",
                        )
                        submitted = st.form_submit_button("发送", use_container_width=False)
                    with st.container(key="cpattach"):
                        _attach_upload()
                if not _stu:
                    _render_storage_row(proj)

            if _stu:
                cards = [
                    ("我的任务", "查看教师发布的实训任务与要求", "doc", "我的任务"),
                    ("学生答疑", "提问并获得引导式提示", "chat", "学生答疑"),
                    ("教师反馈", "查看作业评价与教师评语", "star", "教师反馈"),
                    ("错题回顾", "回顾薄弱知识点与常见错因", "clock", "错题回顾"),
                ]
                rows = [cards[:2], cards[2:]]
            else:
                cards = [
                    ("一键备课", "生成教案、PPT、练习和评分标准", "book", "一键备课"),
                    ("创建实训", "生成 Word、Excel、PPT 实训任务", "tool", "创建实训"),
                    ("学生答疑", "提供引导式提示并汇总错因", "chat", "学生答疑"),
                    ("作业评审", "AI 初评、证据定位和教师复核", "check", "作业评审"),
                    ("课程资源", "管理教材、课件、案例和学生资料", "lib", "课程项目"),
                    ("学情分析", "查看薄弱知识点和下一课建议", "chart", "学情分析"),
                ]
                rows = [cards[:3], cards[3:]]

            with st.container(key="chips"):
                for row in rows:
                    cols = st.columns(len(row))
                    for col, (title, desc, icon, target) in zip(cols, row):
                        with col:
                            with st.container(key=f"qcard_{target}"):
                                st.html(
                                    f'<div class="fm-qcard"><div class="ic">'
                                    f'<span class="fm-mi">{_ICONS[icon]}</span></div>'
                                    f'<div class="tt">{_esc(title)}</div>'
                                    f'<div class="ds">{_esc(desc)}</div></div>'
                                )
                                if st.button(title, key=f"qc_{target}", use_container_width=True):
                                    ss.nav = target
                                    st.rerun()

            if submitted:
                _dispatch_task(ss.get("prompt_text", ""))
                st.rerun()

            _bind_drop_upload()
            _bind_enter_submit()

        if not _stu:
            render_data_source()


# ---------------------------------------------------------------------------
# 数据源：点击入口 + 弹窗上传（首页）；工作台保留内联上传
# ---------------------------------------------------------------------------
def _file_list_html() -> str:
    rows_html = []
    for f in ss.files:
        is_doc = f.get("kind") == "doc"
        if f["status"] == "ok":
            tag = '<span class="fm-tag">原始</span>' if not is_doc else '<span class="fm-tag ok">已解析</span>'
            sub = f'{f["rows"]} 行 × {f["cols"]} 列' if not is_doc else f'{f.get("chars", 0)} 字 · 智谱 {f.get("tool_type", "")}'
        else:
            tag = '<span class="fm-tag err">读取失败</span>'
            sub = _esc(f.get("error", "未知错误"))[:60]
        cls = "fm-ftag csv" if f["ext"] == "CSV" else "fm-ftag"
        rows_html.append(
            f'<div class="fm-list-item"><span class="{cls}">{_esc(f["ext"])}</span>'
            f'<div style="flex:1;min-width:0"><div class="fm-li-t">{_esc(f["name"])}</div>'
            f'<div class="fm-li-s">{sub}</div></div>{tag}</div>'
        )
    return "<div>" + "".join(rows_html) + "</div>"


def _ingest_uploads(up_files) -> list[str]:
    """保存上传文件：表格走 pandas，文档走智谱文件解析；返回本次错误列表。"""
    if not up_files:
        return list(ss.get("load_errors", []))
    sig = tuple(sorted((f.name, f.size) for f in up_files))
    if ss.get("upload_sig") == sig:
        return list(ss.get("load_errors", []))

    ss.upload_sig = sig
    clear_registry()
    clear_documents()
    clear_searches()
    ss.files, ss.docs, ss.required_cols, ss.gate_report, ss.load_errors = [], [], [], None, []
    if "required_cols_widget" in ss:
        del ss["required_cols_widget"]

    loads: list[tuple] = []   # (uf, load_result)，只放表格
    load_errors: list[str] = []

    for uf in up_files:
        suf = Path(uf.name).suffix.lower()
        p = UPLOAD_DIR / f"{uf.file_id}{suf}"
        p.write_bytes(uf.getbuffer())

        if suf in ALLOWED_EXT:
            ld = read_file(str(p))
            loads.append((uf, ld))
            if ld.get("status") == "ok":
                ss.files.append({
                    "name": uf.name,
                    "ext": suf.lstrip(".").upper(),
                    "rows": ld["provenance"]["rows"],
                    "cols": ld["provenance"]["cols"],
                    "status": "ok",
                })
                db.save_file(
                    name=uf.name, ext=suf.lstrip(".").upper(), kind="table",
                    content=uf.getbuffer(), size=uf.size,
                    rows=ld["provenance"]["rows"], cols=ld["provenance"]["cols"],
                    path=str(p), status="ok", project_id=ss.get("current_project_id"),
                )
            else:
                ss.files.append({
                    "name": uf.name,
                    "ext": suf.lstrip(".").upper(),
                    "rows": 0,
                    "cols": 0,
                    "status": "error",
                    "error": ld.get("error", "未知错误"),
                })
                db.save_file(
                    name=uf.name, ext=suf.lstrip(".").upper(), kind="table",
                    content=uf.getbuffer(), size=uf.size,
                    path=str(p), status="error", error=ld.get("error", "未知错误"),
                    project_id=ss.get("current_project_id"),
                )
                load_errors.append(f'{uf.name}：{ld.get("error", "未知错误")}')

        elif suf in DOC_EXT:
            with st.status(f"同步解析：{uf.name}", expanded=True) as stat:
                doc = parse_document_sync(
                    str(p),
                    tool_type=PARSER_TOOL_TYPE,
                    on_progress=lambda msg, _s=stat, _n=uf.name: _s.update(label=f"{_n} · {msg}"),
                )
                if doc.get("status") == "ok":
                    stat.update(
                        label=f"{uf.name} · 解析完成（{doc['chars']} 字 / {doc.get('elapsed_s')}s）",
                        state="complete",
                        expanded=False,
                    )
                else:
                    stat.update(label=f"{uf.name} · 解析失败", state="error")
            if doc.get("status") == "ok":
                prov = doc["provenance"]
                register_document(uf.name, doc["text"], prov)
                ss.docs.append({
                    "name": uf.name,
                    "ext": suf.lstrip(".").upper(),
                    "chars": prov.get("chars", len(doc["text"])),
                    "tool_type": prov.get("tool_type", ""),
                    "task_id": prov.get("task_id"),
                    "result_url": prov.get("result_url"),
                    "status": "ok",
                })
                ss.files.append({
                    "name": uf.name,
                    "ext": suf.lstrip(".").upper(),
                    "kind": "doc",
                    "rows": 0,
                    "cols": 0,
                    "chars": prov.get("chars", len(doc["text"])),
                    "tool_type": prov.get("tool_type", ""),
                    "status": "ok",
                })
                db.save_file(
                    name=uf.name, ext=suf.lstrip(".").upper(), kind="doc",
                    content=uf.getbuffer(), size=uf.size,
                    chars=prov.get("chars", len(doc["text"])),
                    parsed_text=doc["text"], path=str(p), status="ok",
                    project_id=ss.get("current_project_id"),
                )
            else:
                ss.docs.append({"name": uf.name, "status": "error", "error": doc.get("error")})
                ss.files.append({
                    "name": uf.name,
                    "ext": suf.lstrip(".").upper(),
                    "kind": "doc",
                    "rows": 0,
                    "cols": 0,
                    "status": "error",
                    "error": doc.get("error", "解析失败"),
                })
                db.save_file(
                    name=uf.name, ext=suf.lstrip(".").upper(), kind="doc",
                    content=uf.getbuffer(), size=uf.size,
                    path=str(p), status="error", error=doc.get("error", "解析失败"),
                    project_id=ss.get("current_project_id"),
                )
                load_errors.append(f'{uf.name}：{doc.get("error", "解析失败")}')

        else:
            load_errors.append(f"{uf.name}：不支持的格式 {suf}")

    ok_loads = [ld for _, ld in loads if ld.get("status") == "ok"]

    if len(ok_loads) == 1:
        register(ok_loads[0]["_df"], ok_loads[0]["provenance"])
    elif len(ok_loads) > 1:
        merged = merge_loads(ok_loads, how="append")
        if merged.get("status") == "ok":
            register(merged["_df"], merged["provenance"])
        else:
            load_errors.append(f'合并失败：{merged.get("error")}')

    ok_names = [f["name"] for f in ss.files if f["status"] == "ok"]
    db.save_task(
        kind="load",
        prompt=f"加载 {len(ok_names)} 个文件",
        answer="、".join(ok_names) if ok_names else "（无成功文件）",
        status="ok" if ok_names else "error",
        project_id=ss.get("current_project_id"),
    )

    ss.load_errors = load_errors
    return load_errors


def _suggested_module(load_errors: list[str]) -> str | None:
    """根据本次成功上传的文件类型建议跳转到哪个模块。

    规则：
      - 仅表格（xlsx/xls/csv）→ 教学工具
      - 仅文档（PDF/Word/PPT/图片/Markdown…）→ 文件
      - 表格 + 文档混合 → AI 助手（一个入口同时处理两类内容）
      - 全部失败 / 没文件 → None
    """
    if load_errors and not ss.files:
        return None
    table_ok = [f for f in ss.files if f["status"] == "ok" and f.get("kind") != "doc"]
    doc_ok = [f for f in ss.files if f["status"] == "ok" and f.get("kind") == "doc"]
    if not table_ok and not doc_ok:
        return None
    if table_ok and not doc_ok:
        return "教学工具"
    if doc_ok and not table_ok:
        return "文件"
    return "AI 助手"


def _sync_parse_panel() -> None:
    """同步解析：输入服务器本地路径，一次调用完成「创建任务 → 轮询结果」。"""
    with st.expander("同步解析本地文件（输入路径，无需上传）"):
        sp = st.text_input(
            "文件路径",
            placeholder="项目内相对路径或绝对路径，例如 FlowMind-Office-AI-产品规划-v1.1.md",
            key="sync_parse_path",
        )
        c1, c2 = st.columns([1, 2])
        tool = c1.selectbox("解析服务", ["lite", "expert", "prime"], key="sync_parse_tool")
        if c2.button("立即同步解析", key="sync_parse_run", use_container_width=True):
            if not sp.strip():
                st.warning("请先填写文件路径")
            else:
                target = Path(sp.strip())
                if not target.is_absolute():
                    target = (ROOT / target).resolve()
                with st.status("同步解析中…", expanded=True) as stat:
                    d = parse_document_sync(
                        str(target),
                        tool_type=tool,
                        on_progress=lambda msg, _s=stat: _s.update(label=msg),
                    )
                    if d["status"] == "ok":
                        register_document(target.name, d["text"], d["provenance"])
                        ss.docs.append({
                            "name": target.name,
                            "ext": target.suffix.lstrip(".").upper(),
                            "chars": d["chars"],
                            "tool_type": d["provenance"].get("tool_type", ""),
                            "task_id": d.get("task_id"),
                            "result_url": d.get("result_url"),
                            "status": "ok",
                        })
                        stat.update(
                            label=f"解析完成：{d['chars']} 字 / {d.get('elapsed_s')}s",
                            state="complete",
                            expanded=False,
                        )
                    else:
                        stat.update(label="解析失败", state="error")
                if d["status"] == "ok":
                    st.caption(f"{target.name} · task {d.get('task_id')}")
                    if d.get("result_url"):
                        st.markdown(f"[下载解析结果]({d['result_url']})")
                    st.text(d["text"][:800])
                    st.caption("已注册到当前会话，可直接在对话框提问。")
                else:
                    st.error(d.get("error", "解析失败"))


def _attach_upload() -> None:
    """快捷图标里的附件上传（数据源）：表格直接读取，文档交给解析服务。"""
    up_files = st.file_uploader(
        "添加附件",
        type=[e.lstrip(".") for e in sorted(UPLOAD_EXT)],
        accept_multiple_files=True,
        key="hero_attach",
        label_visibility="collapsed",
    )
    _ingest_uploads(up_files)


_DROP_JS = """
<script>
(function(){
  var w = window.parent, d;
  try { d = w.document; } catch (e) { return; }
  /* 每次注入都重建监听：先移除旧的，避免重复触发 */
  if (w.__zyDropFn) {
    w.removeEventListener('dragover', w.__zyDropFn.over, true);
    w.removeEventListener('dragleave', w.__zyDropFn.leave, true);
    w.removeEventListener('drop', w.__zyDropFn.drop, true);
  }
  w.__zhiyiDropBound = true;

  function hasFiles(ev){
    var t = ev.dataTransfer; if (!t) { return false; }
    var ty = t.types;
    if (ty) { for (var i = 0; i < ty.length; i++) { if (ty[i] === 'Files') { return true; } } }
    if (t.files && t.files.length) { return true; }
    return false;
  }
  function zoneOfPath(ev){
    var path = (typeof ev.composedPath === 'function') ? ev.composedPath() : [];
    for (var i = 0; i < path.length; i++) {
      var el = path[i];
      if (!el || !el.closest) { continue; }
      if (el.closest('.st-key-herobox')) { return { box: el.closest('.st-key-herobox'), sel: '.st-key-cpattach input[type=file]' }; }
      if (el.closest('.st-key-composer')) { return { box: el.closest('.st-key-composer'), sel: '.st-key-cpattach2 input[type=file]' }; }
    }
    var t = ev.target;
    if (t && t.closest) {
      var h = t.closest('.st-key-herobox'); if (h) { return { box: h, sel: '.st-key-cpattach input[type=file]' }; }
      var c = t.closest('.st-key-composer'); if (c) { return { box: c, sel: '.st-key-cpattach2 input[type=file]' }; }
    }
    return null;
  }
  var over = function(ev){
    var z = zoneOfPath(ev); if (!z || !hasFiles(ev)) { return; }
    ev.preventDefault(); ev.stopPropagation(); z.box.classList.add('fm-drop');
  };
  var leave = function(ev){
    var z = zoneOfPath(ev); if (z) { z.box.classList.remove('fm-drop'); }
  };
  var drop = function(ev){
    var z = zoneOfPath(ev); if (!z || !hasFiles(ev)) { return; }
    ev.preventDefault(); ev.stopPropagation(); z.box.classList.remove('fm-drop');
    var input = d.querySelector(z.sel);
    if (!input) { return; }
    try {
      var dt = new w.DataTransfer();
      var files = ev.dataTransfer.files;
      for (var i = 0; i < files.length; i++) { dt.items.add(files[i]); }
      input.files = dt.files;
      input.dispatchEvent(new w.Event('change', { bubbles: true }));
    } catch (err) {
      /* DataTransfer 构造失败时回退：直接设置 files（部分浏览器允许） */
      try { input.files = ev.dataTransfer.files; input.dispatchEvent(new w.Event('change', { bubbles: true })); } catch (e2) {}
    }
  };
  w.addEventListener('dragover', over, true);
  w.addEventListener('dragleave', leave, true);
  w.addEventListener('drop', drop, true);
  w.__zyDropFn = { over: over, leave: leave, drop: drop };
})();
</script>
"""


def _bind_drop_upload() -> None:
    """把文件直接拖到首页输入卡片上即可上传（写入附件组件的隐藏 input）。"""
    components.html(_DROP_JS, height=0)


_ENTER_JS = """
<script>
(function(){
  var w = window.parent, d;
  try { d = w.document; } catch (e) { return; }

  /* ---------- 输入框高度自适应 ----------
     每次注入都重新定义并替换定时器：旧页面里遗留的计时器闭包会一直跑旧逻辑，
     只清理标记变量是不够的，必须 clearInterval 掉旧的再建新的。 */
  var nativeGrow = !!(w.CSS && w.CSS.supports && w.CSS.supports('field-sizing', 'content'));
  var fit = function(ta){
    if (nativeGrow) {
      /* 新内核用 field-sizing:content 原生跟随，去掉写死的像素高度，缩放时由浏览器重算 */
      ta.style.removeProperty('height');
      ta.__zyKey = null;
      return;
    }
    /* 旧内核回退：先归零再测量，否则框体只会变高、不会跟着内容或缩放变矮 */
    ta.style.setProperty('height', 'auto', 'important');
    var cap = Math.max(120, w.innerHeight * 0.4);
    var h = Math.min(ta.scrollHeight, cap);
    ta.style.setProperty('height', Math.max(h, 48) + 'px', 'important');
    ta.__zyKey = null;
  };
  var sync = function(){
    var tas = d.querySelectorAll('.st-key-promptbox textarea');
    var base = w.innerWidth + 'x' + w.innerHeight + '@' + (w.devicePixelRatio || 1);
    for (var i = 0; i < tas.length; i++) {
      var ta = tas[i];
      /* 视口/缩放/宽度/内容任一变化都重新计算；用 offsetWidth 避免滚动条造成的反复抖动 */
      var key = base + '|' + ta.offsetWidth + '|' + ta.value.length;
      if (ta.__zyKey === key) { continue; }
      ta.__zyKey = key;
      fit(ta);
    }
  };
  w.__zhiyiGrowSync = sync;
  clearInterval(w.__zhiyiGrow);
  clearInterval(w.__zhiyiGrowTimer);
  w.__zhiyiGrowTimer = setInterval(function(){
    if (w.__zhiyiGrowSync) { w.__zhiyiGrowSync(); }
  }, 200);
  if (!w.__zhiyiGrowBound) {
    w.__zhiyiGrowBound = 1;
    var kick = function(){ if (w.__zhiyiGrowSync) { w.__zhiyiGrowSync(); } };
    w.addEventListener('resize', kick);
    w.addEventListener('orientationchange', kick);
    if (w.visualViewport) { w.visualViewport.addEventListener('resize', kick); }
    d.addEventListener('input', function(ev){
      if (ev.target && ev.target.tagName === 'TEXTAREA' && w.__zhiyiGrowSync) {
        w.__zhiyiGrowSync();
      }
    }, true);
  }
  sync();

  /* ---------- 回车提交（只绑定一次） ---------- */
  if (w.__zhiyiEnterVer === 7) { return; }
  w.__zhiyiEnterVer = 7;
  d.addEventListener('keydown', function(ev){
    var t = ev.target;
    if (!t || t.tagName !== 'TEXTAREA') { return; }
    if (ev.key !== 'Enter' || ev.shiftKey || ev.ctrlKey || ev.metaKey || ev.altKey) { return; }
    var el = t.parentElement, btn = null, depth = 0;
    while (el && depth < 12) {
      var b = el.querySelector ? el.querySelector('[data-testid="stFormSubmitButton"] button') : null;
      if (b) { btn = b; break; }
      el = el.parentElement; depth++;
    }
    if (!btn) { return; }
    ev.preventDefault();
    btn.click();
  }, true);
})();
</script>
"""


def _bind_enter_submit() -> None:
    """首页与对话输入框：Enter 提交，Shift+Enter 换行。"""
    components.html(_ENTER_JS, height=0)


def _ds_status(compact: bool = False) -> None:
    """质量闸门标签；首页额外给出最近任务 / 最近文件入口。"""
    load_errors = list(ss.get("load_errors", []))
    cur = _REGISTRY.get("current")
    if cur and "required_cols_widget" in ss:
        ss.required_cols = [c for c in ss["required_cols_widget"] if c in cur["df"].columns]

    gate = None
    if cur:
        gate = quality_gate({"status": "ok", "_df": cur["df"]}, required=list(ss.required_cols))
        ss.gate_report = gate
    else:
        ss.gate_report = None

    tags = []
    if cur:
        if not gate["ok"]:
            tags.append('<span class="fm-tag err"><span class="fm-dot"></span>质量闸门阻断</span>')
        if compact:
            tags.append(f'<span class="fm-tag">{cur["df"].shape[0]} 行 × {cur["df"].shape[1]} 列</span>')
        for c in gate.get("null_rate_columns", []):
            tags.append(f'<span class="fm-tag warn">{_esc(c)}</span>')
    docs = get_documents()
    if docs:
        tags.append(f'<span class="fm-tag ok">{len(docs)} 份文档已解析</span>')
    if load_errors:
        tags.append(f'<span class="fm-tag err">{len(load_errors)} 个文件处理失败</span>')
    if tags:
        st.html(
            f'<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;'
            f'padding-top:{24 if compact else 6}px">'
            + "".join(tags) + "</div>"
        )


def render_data_source(compact: bool = False) -> None:
    if compact:
        st.html('<div class="fm-muted" style="margin:0 0 3px 1px">数据源 · 上传真实文件</div>')
        ds_l, ds_r = st.columns([1.15, 1], gap="small")
        with ds_l:
            up_files = st.file_uploader(
                "上传文件",
                type=[e.lstrip(".") for e in sorted(UPLOAD_EXT)],
                accept_multiple_files=True,
                label_visibility="collapsed",
            )
            _ingest_uploads(up_files)

        # compact 模式也提示跳转（当前模块就是 suggest 的目标时不打扰）
        if compact:
            errors = ss.get("load_errors", [])
            suggested = _suggested_module(errors)
            current_view = ss.get("nav", "首页")
            if suggested and suggested != current_view \
                    and (not ss.get("last_route") or ss.last_route != suggested):
                ss.last_route = suggested
                st.info(f"检测到文件类型 → 建议跳转到「{suggested}」处理。")
                if st.button(f"前往 「{suggested}」", key=f"auto_route_btn_cpt_{suggested}",
                             type="primary", use_container_width=True):
                    ss.nav = suggested
                    st.rerun()
        with ds_r:
            _ds_status(compact=True)

        cur = _REGISTRY.get("current")
        if ss.files or cur or ss.docs:
            with st.expander(f"已加载文件与质量闸门 · {len(ss.files)} 个文件"):
                if ss.files:
                    st.html(_file_list_html())

                if cur:
                    ss.required_cols = st.multiselect(
                        "质量闸门关键列（可选）",
                        options=list(cur["df"].columns),
                        key="required_cols_widget",
                        placeholder="选择必须存在且非空的列；不选则只做结构展示",
                    )
                docs = get_documents()
                if docs:
                    st.caption("已解析文档：" + "、".join(f"{n}（{len(d['content'])} 字）" for n, d in docs.items()))
                gate = ss.get("gate_report")
                if gate and not gate["ok"]:
                    st.error(gate["message"])
                for e in ss.get("load_errors", []):
                    st.error(e)
    else:
        st.html('<div class="fm-hr"></div>')
        _ds_status(compact=False)


# ---------------------------------------------------------------------------
# 文件 / 任务：SQLite 持久化历史（重启不丢，内容存数据库可恢复）
# ---------------------------------------------------------------------------
def _load_db_file_to_session(file_id: int) -> str:
    """把数据库里的历史文件恢复为当前会话数据；返回提示文案。"""
    f = db.get_file(file_id, with_content=True)
    if not f:
        return "记录不存在"
    if not f.get("content"):
        return "该记录没有保存文件内容，无法恢复"
    clear_registry()
    clear_documents()
    clear_searches()
    suffix = "." + str(f["ext"]).lower()
    p = UPLOAD_DIR / f"db_{f['id']}{suffix}"
    p.write_bytes(f["content"])

    if f.get("kind") == "doc":
        text = f.get("parsed_text")
        if not text:
            # 数据库只存了原文：重新走一次智谱解析
            doc = parse_document_sync(str(p), tool_type=PARSER_TOOL_TYPE)
            if doc.get("status") != "ok":
                return f'重新解析失败：{doc.get("error", "未知错误")}'
            text = doc["text"]
        register_document(f["name"], text, {
            "file": f["name"], "chars": len(text), "tool_type": "db",
        })
        ss.docs = [{"name": f["name"], "ext": f["ext"], "chars": len(text),
                    "tool_type": "db", "status": "ok"}]
        ss.files = [{"name": f["name"], "ext": f["ext"], "kind": "doc",
                     "rows": 0, "cols": 0, "chars": len(text),
                     "tool_type": "db", "status": "ok"}]
        return f'已恢复文档「{f["name"]}」（{len(text)} 字）到当前会话'

    ld = read_file(str(p))
    if ld.get("status") != "ok":
        return f'重新读取失败：{ld.get("error", "未知错误")}'
    register(ld["_df"], ld["provenance"])
    ss.docs = []
    ss.files = [{"name": f["name"], "ext": f["ext"],
                 "rows": ld["provenance"]["rows"],
                 "cols": ld["provenance"]["cols"], "status": "ok"}]
    return (f'已恢复表格「{f["name"]}」（{ld["provenance"]["rows"]} 行 × '
            f'{ld["provenance"]["cols"]} 列）到当前会话')


def render_files_page() -> None:
    _ensure_current_project()
    files = db.list_files(project_id=ss.current_project_id, limit=200)
    with st.container(key="panel"):
        st.html(
            f'<div class="fm-cardhead"><h2>文件</h2>'
            f'<div class="r">SQLite · {len(files)} 条 · 重启不丢</div></div>'
        )
        if not files:
            st.html('<div class="fm-empty">数据库里还没有文件。<br>'
                    '在「教学工具」或首页上传后，文件内容会持久保存到数据库。</div>')
        for f in files:
            is_doc = f.get("kind") == "doc"
            ok = f.get("status") == "ok"
            cls = "fm-ftag csv" if f["ext"] == "CSV" else "fm-ftag"
            if ok:
                sub = (f'{f["rows"]} 行 × {f["cols"]} 列' if not is_doc
                       else f'{f.get("chars", 0)} 字 · 已解析')
            else:
                sub = _esc(f.get("error") or "失败")[:60]
            tag = ('<span class="fm-tag ok">已解析</span>' if ok and is_doc
                   else '<span class="fm-tag">原始</span>' if ok
                   else '<span class="fm-tag err">异常</span>')
            st.html(
                f'<div class="fm-list-item"><span class="{cls}">{_esc(f["ext"])}</span>'
                f'<div style="flex:1;min-width:0"><div class="fm-li-t">{_esc(f["name"])}</div>'
                f'<div class="fm-li-s">{sub} · {_human_size(f.get("size"))} · '
                f'{_fmt_time(f.get("created_at"))}</div></div>{tag}</div>'
            )
            b1, b2, b3, _gap = st.columns([1.1, 1.1, 1.1, 4.2])
            if b1.button("加载到会话", key=f"fload_{f['id']}",
                         disabled=not ok or not f.get("has_content")):
                st.success(_load_db_file_to_session(f["id"]))
            if is_doc and f.get("has_text"):
                if b2.button("查看正文", key=f"ftext_{f['id']}"):
                    ss[f"show_text_{f['id']}"] = not ss.get(f"show_text_{f['id']}")
                    st.rerun()
            if b3.button("删除", key=f"fdel_{f['id']}"):
                db.delete_file(f["id"])
                try:
                    if f.get("path"):
                        Path(f["path"]).unlink(missing_ok=True)
                except Exception:
                    pass
                st.toast("已删除")
                st.rerun()
            if ss.get(f"show_text_{f['id']}"):
                st.text((db.get_file_text(f["id"]) or "")[:3000])


def render_tasks_page() -> None:
    _ensure_current_project()
    tasks = db.list_tasks(project_id=ss.current_project_id, limit=200)
    with st.container(key="panel"):
        st.html(
            f'<div class="fm-cardhead"><h2>任务</h2>'
            f'<div class="r">SQLite · {len(tasks)} 条 · 重启不丢</div></div>'
        )
        if not tasks:
            st.html('<div class="fm-empty">还没有任务记录。<br>'
                    '上传文件、发起分析后会自动写入数据库。</div>')
        for t in tasks:
            ok = t.get("status") == "ok"
            is_agent = t.get("kind") == "agent"
            n_tools = len(t.get("tools_used") or [])
            dur = f' · {t["duration_s"]}s' if t.get("duration_s") is not None else ""
            sub = (f'{_fmt_time(t.get("created_at"))}{dur}'
                   + (f' · 工具调用 {n_tools} 次' if is_agent else ""))
            icon = _ic('<path d="M5 12.5l4.5 4.5L19 7"/>') if ok \
                else _ic('<path d="M12 9v4M12 17h.01"/><circle cx="12" cy="12" r="9"/>')
            tag = "已执行" if is_agent and ok else "已完成" if ok else "需处理"
            st.html(
                f'<div class="fm-list-item"><div class="fm-fi">{icon}</div>'
                f'<div style="flex:1;min-width:0"><div class="fm-li-t">{_esc(t["prompt"])}</div>'
                f'<div class="fm-li-s">{_esc(sub)}</div></div>'
                f'<span class="fm-tag {"ok" if ok else "err"}">{tag}</span></div>'
            )
            if is_agent and t.get("answer"):
                with st.expander("查看回答"):
                    st.markdown(t["answer"])
            elif not is_agent and t.get("answer"):
                st.caption(f"文件：{t['answer']}")
            d1, _gap = st.columns([1.1, 6.4])
            if d1.button("删除", key=f"tdel_{t['id']}"):
                db.delete_task(t["id"])
                st.toast("已删除")
                st.rerun()


# ---------------------------------------------------------------------------
# 项目管理
# ---------------------------------------------------------------------------
def render_projects_page() -> None:
    """列出全部项目，支持切换/新建/删除，点击可展开查看详情。"""
    _ensure_current_project()
    projects = db.list_projects()

    _folder_icon = _ic('<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/>')

    with st.container(key="panel"):
        st.html(
            f'<div class="fm-cardhead"><h2>项目管理</h2>'
            f'<div class="r">当前：<b>{_esc(ss.current_project_name)}</b></div></div>'
        )

        # 新建项目表单
        with st.expander("＋ 新建项目"):
            with st.form("new_proj_page", clear_on_submit=True):
                st.text_input("项目名称", key="np_name", placeholder="例如：12月财务月度分析")
                st.text_input("描述（可选）", key="np_desc")
                st.checkbox("在本地创建同名文件夹（任务文件将保存在这里）", value=True, key="np_folder")
                ok = st.form_submit_button("创建并切换到此项目", type="primary")
                if ok:
                    nm = (ss.get("np_name") or "").strip()
                    if not nm:
                        st.error("请填写项目名称")
                    else:
                        try:
                            folder = None
                            if ss.get("np_folder", True):
                                fp = PROJECT_DIR / _safe_dirname(nm)
                                fp.mkdir(parents=True, exist_ok=True)
                                folder = str(fp)
                            pid = db.create_project(nm, ss.get("np_desc", "") or "", folder=folder)
                            ss.current_project_id = pid
                            ss.current_project_name = nm
                            st.success(f"已创建并切换到「{nm}」" + (f" · 文件夹 {folder}" if folder else ""))
                        except Exception as e:
                            st.error(str(e))

        if not projects:
            st.html('<div class="fm-empty">数据库里还没有项目。</div>')

        for p in _visible_projects(projects):
            is_cur = p["id"] == ss.current_project_id
            bg = "background:var(--accent-soft);" if is_cur else ""
            cur_tag = ' <span class="fm-tag acc" style="margin-left:6px">当前</span>' if is_cur else ""
            _pf = _project_folder(p)
            _folder_sub = f' · {_path_html(str(_pf))}' if _pf else " · 未建本地文件夹"
            html_row = (
                f'<div class="fm-list-item" style="{bg}padding:10px 12px;border-radius:9px">'
                f'<div class="fm-fi" style="width:30px;height:30px">{_folder_icon}</div>'
                f'<div style="flex:1;min-width:0"><div class="fm-li-t" style="font-size:13px;font-weight:600">'
                f'{_esc(p["name"])}{cur_tag}</div>'
                f'<div class="fm-li-s">{_esc(p.get("description") or "无描述")} · '
                f'{p["file_count"]} 文件 · {p["task_count"]} 任务 · {_fmt_time(p["created_at"])}</div>'
                f'<div class="fm-li-s" style="font-size:10.5px;opacity:.8">文件夹{_folder_sub}</div></div>'
                f'</div>'
            )
            st.html(html_row)
            # 操作行
            with st.container(key=f"projops_{p['id']}"):
                c1, c2, c3, c4, _g = st.columns([1.2, 1.2, 1.4, 1.2, 5.1])
                if not is_cur:
                    if c1.button("切换", key=f"pswitch_{p['id']}", use_container_width=True):
                        ss.current_project_id = p["id"]
                        ss.current_project_name = p["name"]
                        st.toast(f"已切换到「{p['name']}」")
                        st.rerun()
                else:
                    c1.html('<div style="font-size:11px;color:var(--text-3);padding:6px 0">当前项目</div>')

                # 展开查看详情
                exp_key = f"pexp_{p['id']}"
                if c2.button("查看详情", key=f"pview_{p['id']}", use_container_width=True):
                    ss[exp_key] = not ss.get(exp_key, False)
                    st.rerun()

                # 删除：其下文件与任务保留为未归属
                if c3.button("删除", key=f"pdel_{p['id']}", use_container_width=True):
                    db.delete_project(p["id"])
                    if is_cur:
                        ss.current_project_id = None
                        ss.current_project_name = ""
                    st.toast(f"已删除「{p['name']}」，其下文件与任务保留为未归属")
                    st.rerun()

                # 打开项目文件夹
                if c4.button("打开文件夹", key=f"pfolder_{p['id']}", use_container_width=True):
                    if _pf:
                        try:
                            os.startfile(str(_pf))
                        except Exception as e:
                            st.toast(f"打开失败：{e}")
                    else:
                        st.toast("该项目没有本地文件夹")

            if ss.get(exp_key):
                # 显示该项目的文件与任务概要
                _pfiles = db.list_files(project_id=p["id"], limit=50)
                _pt = db.list_tasks(project_id=p["id"], limit=50)
                st.caption(f"文件 {len(_pfiles)} 条：" +
                           ("、".join(f["name"] for f in _pfiles[:5]) + ("…" if len(_pfiles) > 5 else "")
                            if _pfiles else "（无）"))
                st.caption(f"任务 {len(_pt)} 条：" +
                           ("、".join(t["prompt"][:20] for t in _pt[:3]) + ("…" if len(_pt) > 3 else "")
                            if _pt else "（无）"))
                st.divider()

    # ---- 最近任务（当前项目） ----
    _recent = db.recent_tasks(limit=8, project_id=ss.current_project_id)
    with st.container(key="panel-recent-tasks"):
        st.html(
            f'<div class="fm-cardhead"><h2>最近任务</h2>'
            f'<div class="r">{_esc(ss.current_project_name)} · {len(_recent)} 条</div></div>'
        )
        if not _recent:
            st.html('<div class="fm-empty">当前项目还没有任务记录。<br>'
                    '在 AI 助手提问或上传文件后，会自动记录到这里。</div>')
        for t in _recent:
            ok = t.get("status") == "ok"
            is_agent = t.get("kind") == "agent"
            tag_cls = "ok" if ok else "err"
            tag_txt = "已执行" if is_agent and ok else ("已完成" if ok else "失败")
            dur = f' · {t["duration_s"]}s' if t.get("duration_s") is not None else ""
            icon = _ic('<path d="M5 12.5l4.5 4.5L19 7"/>') if ok \
                else _ic('<path d="M12 9v4M12 17h.01"/><circle cx="12" cy="12" r="9"/>')
            row = (
                f'<div class="fm-list-item"><div class="fm-fi" style="width:24px;height:24px">'
                f'{icon}</div><div style="flex:1;min-width:0">'
                f'<div class="fm-li-t">{_esc(t["prompt"])}</div>'
                f'<div class="fm-li-s">{_fmt_time(t.get("created_at"))}{dur}</div></div>'
                f'<span class="fm-tag {tag_cls}">{tag_txt}</span></div>'
            )
            st.html(row)
            if t.get("answer"):
                with st.expander("查看回答" if is_agent else "查看详情"):
                    if is_agent:
                        st.markdown(t["answer"])
                    else:
                        st.write(t["answer"])
        b1, b2, _g = st.columns([1.4, 1.4, 5.2])
        if b1.button("全部任务", key="pj_all_tasks", use_container_width=True):
            ss.nav = "任务"
            st.rerun()
        if b2.button("全部文件", key="pj_all_files", use_container_width=True):
            ss.nav = "文件"
            st.rerun()


# ---------------------------------------------------------------------------
# 对话
# ---------------------------------------------------------------------------


def _steps_to_json(steps) -> list[dict]:
    out = []
    for action, obs in steps:
        try:
            j = json.loads(obs)
            kept = {k: v for k, v in j.items() if k in (
                "status", "error", "provenance", "rows", "rows_before", "rows_after", "exported_to",
                "missing_fields", "columns_kept", "grouped_rows",
                "chars", "total_chars", "range", "hit_count",
            )}
        except Exception:
            kept = None
        out.append({
            "tool": str(getattr(action, "tool", "tool")),
            "input": str(getattr(action, "tool_input", ""))[:400],
            "obs": kept if kept is not None else str(obs)[:800],
        })
    return out


def _render_message(m: dict) -> None:
    if m["role"] == "user":
        st.html(f'<div class="fm-me"><div class="b">{_esc(m["text"])}</div></div>')
        return
    if m.get("error"):
        st.markdown(f'<span class="fm-tag err"><span class="fm-dot"></span>执行失败</span>', unsafe_allow_html=True)
        st.error(m["text"])
    else:
        st.markdown(m["text"])
    if m.get("steps"):
        with st.expander(f"工具调用轨迹 · {len(m['steps'])} 步（可追溯）"):
            for i, s in enumerate(m["steps"], 1):
                st.markdown(f"**第 {i} 步** · `{s['tool']}`")
                st.code(s["input"], language="json")
                if isinstance(s["obs"], dict):
                    st.json(s["obs"])
                else:
                    st.code(s["obs"], language=None)


def render_ai_page(auto_start: bool = False) -> None:
    """AI 教学助手：欢迎页 + 示例任务 + 底部对话输入区。"""
    proj = db.get_project(ss["current_project_id"]) if ss.get("current_project_id") else None
    ov = db.course_overview(proj["id"]) if proj else None
    model = os.getenv("LLM_MODEL", LLM_MODEL)
    course_name = proj["name"] if proj else "未选择课程"
    files_n = ov["files_total"] if ov else 0

    st.html(
        '<div class="fm-ai-hero">'
        "<h1>AI 教学助手</h1>"
        "<p>结合当前课程资料，回答问题、设计课堂任务、分析学生作业。</p>"
        '<div class="fm-ai-meta">'
        f'<span class="fm-tag">当前课程：{_esc(course_name)}</span>'
        f'<span class="fm-tag">可用课程资料：{files_n} 份</span>'
        f'<span class="fm-tag">当前模型：{_esc(model)}</span>'
        "</div></div>"
    )

    if not proj:
        st.html('<div class="fm-note">使用步骤：选择课程 → 上传课程资料 → 开始提问。</div>')
        c1, c2, _ = st.columns([1.3, 1.3, 3.4])
        with c1:
            if st.button("选择课程", key="ai_pick_course", type="primary",
                         use_container_width=True):
                ss.nav = "课程项目"
                st.rerun()
        with c2:
            if st.button("创建课程项目", key="ai_new_course", use_container_width=True):
                ss["edu_open_new"] = True
                ss.nav = "课程项目"
                st.rerun()
    else:
        if files_n == 0:
            st.html('<div class="fm-note">当前课程还没有课程资料。先到「课程项目」上传教材或课件，'
                    "助手会优先依据资料回答。</div>")
        st.html('<div class="fm-ai-sugg">你可以直接让我：</div>')
        examples = [
            "根据课程资料设计一堂 45 分钟课程",
            "将 Excel 数据转换成课堂案例",
            "分析学生作业中的共性问题",
            "生成实训任务和评分量规",
        ]
        for row_start in (0, 2):
            cols = st.columns(2)
            for idx, text in zip((row_start, row_start + 1), examples[row_start:row_start + 2]):
                with cols[idx - row_start]:
                    with st.container(key=f"aicard_{idx}"):
                        st.html(f'<div class="fm-example">{_esc(text)}</div>')
                        if st.button(text, key=f"aiex_{idx}", use_container_width=True):
                            ss["composer_text"] = text
                            st.rerun()

    render_chat(with_header=False, auto_start=auto_start)


def render_chat(with_header: bool = True, auto_start: bool = False) -> None:
    # 任务生成的文件统一写入当前项目的本地文件夹
    _cur_proj = db.get_project(ss.get("current_project_id")) if ss.get("current_project_id") else None
    set_output_dir(_project_folder(_cur_proj))

    if with_header and VIEW not in ("教学工具", "AI 助手"):
        st.html('<div class="fm-sec-title" style="margin-top:18px">对话</div>')

    if not ss.chat_history and VIEW != "AI 助手":
        _empty = (
            "还没有对话。直接描述需求即可开始。"
            if VIEW == "教学工具"
            else "还没有对话。上传数据，或直接粘贴表格数据并说明要生成的文件。"
        )
        st.html(f'<div class="fm-empty">{_esc(_empty)}</div>')

    for _m in ss.chat_history:
        _render_message(_m)

    # 输入区：附件 + 模型选择 + 输入 + 发送（同一区域）
    def _take_composer() -> None:
        ss.pending_q = (ss.get("composer_text") or "").strip()

    with st.container(key="composer"):
        with st.container(key="cpattach2"):
            _attach_upload()
        with st.form("composer_form", border=False, clear_on_submit=True):
            if VIEW == "AI 助手":
                _cm, _ci, _cs = st.columns([2.2, 6.4, 1.1])
                with _cm:
                    st.selectbox("模型", list(_MODEL_PROVIDERS), key="ai_model_sel",
                                 label_visibility="collapsed")
            else:
                _ci, _cs = st.columns([8.6, 1.1])
            with _ci:
                st.text_area(
                    "输入需求",
                    key="composer_text",
                    placeholder=("想完成什么教学任务？可以直接描述。"
                                 if VIEW == "AI 助手" else "想做什么事，直接跟我说"),
                    label_visibility="collapsed",
                    height=44,
                )
            with _cs:
                st.form_submit_button(
                    "↑", on_click=_take_composer, use_container_width=False,
                    disabled=not (ss.get("composer_text") or "").strip(),
                )

    question = (ss.get("pending_q") or "").strip()
    ss.pending_q = ""

    trigger = question or (ss.get("prompt_text", "").strip() if auto_start else "")

    if VIEW == "AI 助手":
        _sel = ss.get("ai_model_sel")
        if _sel and _sel != ss.get("model_provider"):
            if _apply_model_provider(_sel):
                ss.model_provider = _sel

    if trigger:
        cur = _REGISTRY.get("current")
        docs = get_documents()
        if not cur and not docs and not _requests_excel_output(trigger) and VIEW not in (
            "教学工具", "AI 助手",
        ):
            st.error("请先上传并成功加载文件，或直接在需求中附上表格数据。Agent 不会凭空分析。")
        elif cur and ss.gate_report and not ss.gate_report.get("ok"):
            st.error("数据质量闸门未通过，已阻断分析。请先按提示修正关键列或调整校验列。")
        else:
            user_msg = {"role": "user", "text": trigger}
            ss.chat_history.append(user_msg)
            _render_message(user_msg)

            parts = []
            if cur:
                prov = cur["provenance"]
                parts.append(
                    f"当前会话已加载真实数据：文件={prov.get('file')}，工作表={prov.get('sheet')}，"
                    f"{prov.get('rows')} 行 × {prov.get('cols')} 列；列名={list(cur['df'].columns)}。"
                    f"请直接调用 describe_dataframe 获取结构，不要再次要求用户提供文件路径。"
                )
            if not cur and _requests_excel_output(trigger):
                parts.append(
                    "当前没有预加载表格。只能使用用户本轮明确提供的数据调用 create_dataframe_from_text 建表；"
                    "缺少有效数据时请用户补充，不得编造。建表成功后按用户要求导出 xlsx。"
                )
            if docs:
                parts.append(
                    "当前会话已解析文档："
                    + "；".join(
                        f"{name}（{len(d['content'])} 字，task_id={d['provenance'].get('task_id')}，"
                        f"解析服务={d['provenance'].get('tool_type')}）"
                        for name, d in docs.items()
                    )
                    + "。正文已注册，请直接调用 list_documents / read_document 读取，"
                    "不要要求用户重新上传，也不要编造正文之外的内容。"
                )
            if VIEW == "教学工具":
                parts.append(
                    "当前在教学工具：既能做表格数据整理与 Excel 导出，也能撰写/改写 Word 正文、"
                    "梳理 PPT 大纲与讲稿；按需输出可直接使用的 Markdown。"
                )
            ctx = "\n".join(parts)
            hist = [(m["role"], m["text"]) for m in ss.chat_history[:-1] if not m.get("error")][-6:]

            with st.spinner("Agent 调用确定性工具计算中…"):
                from app.agent import run as agent_run
                _t0 = time.time()
                try:
                    result = agent_run(trigger, hist, context=ctx)
                except Exception as e:  # 配置缺失等
                    result = {"status": "error", "error": f"{e.__class__.__name__}: {e}"}
                _dur = round(time.time() - _t0, 1)

            if result.get("status") == "ok":
                asst = {
                    "role": "assistant",
                    "text": result.get("output", ""),
                    "steps": _steps_to_json(result.get("intermediate_steps", [])),
                }
                db.save_task(
                    kind="agent", prompt=trigger, answer=asst["text"],
                    tools_used=[s["tool"] for s in asst["steps"]],
                    status="ok", duration_s=_dur,
                    project_id=ss.get("current_project_id"),
                )
            else:
                asst = {"role": "assistant", "text": result.get("error", "未知错误"), "error": True}
                db.save_task(
                    kind="agent", prompt=trigger, answer=asst["text"],
                    status="error", duration_s=_dur,
                    project_id=ss.get("current_project_id"),
                )
            ss.chat_history.append(asst)
            ss.pending_prompt = ""

            st.rerun()


# ---------------------------------------------------------------------------
# 其他视图
# ---------------------------------------------------------------------------
def _excel_analysis_block() -> None:
    """教学工具内的「数据概览」：质量闸门 + 前 50 行真实数据。"""
    cur = _REGISTRY.get("current")
    if not cur:
        st.html('<div class="fm-empty">还没有可分析的数据。上传表格，或在对话中粘贴数据建表后即可查看。</div>')
        return

    df, p = cur["df"], cur["provenance"]
    gate = quality_gate({"status": "ok", "_df": df}, required=list(ss.required_cols))
    gate_tag = "" if gate["ok"] else '<span class="fm-tag err"><span class="fm-dot"></span>质量闸门未通过</span>'
    st.html(
        '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">'
        f'<span class="fm-tag">{_esc(p.get("file"))}</span>'
        f'<span class="fm-tag">{df.shape[0]} 行 × {df.shape[1]} 列</span>'
        f'{gate_tag}</div>'
    )
    st.caption(f"工作表：{p.get('sheet') or '—'} · 以下为前 50 行真实数据预览，可直接排序与查看")
    st.dataframe(df.head(50), use_container_width=True)


def _excel_report_block() -> None:
    """教学工具内的「报告工坊」：把真实计算结果整理成可交付报告。"""
    st.html(
        '<p class="fm-hero-p" style="margin:0 0 6px">基于当前已加载的真实数据与已解析文档，'
        '把结论整理成结构清晰的报告（背景 / 数据范围 / 关键数字 / 结论与建议）。'
        '所有数字都必须来自工具计算结果，不做估算。</p>'
    )
    if not _has_data():
        st.html('<div class="fm-empty" style="padding:8px 0 0">当前还没有数据。'
                '在上方上传文件后，即可在这里生成报告。</div>')


def _test_llm(url: str, key: str) -> tuple[bool, str]:
    """真实的连通性探测：调用 /models 端点，不伪造成功。"""
    import urllib.error
    import urllib.request

    if not key or key.startswith("sk-REPLACE"):
        return False, "未配置 API Key"
    req = urllib.request.Request(url.rstrip("/") + "/models",
                                 headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            return True, f"连接成功（HTTP {resp.status}）"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, f"鉴权失败（HTTP {e.code}），请检查 API Key"
        return True, f"服务可达（HTTP {e.code}）"
    except Exception as e:
        return False, f"连接失败：{e}"


def _mask_key(key: str) -> str:
    if not key or key.startswith("sk-REPLACE"):
        return "未配置"
    if len(key) <= 8:
        return "****"
    return f"{key[:3]}****{key[-4:]}"


def render_settings() -> None:
    edu_ui._sec("设置", "仅当前进程")
    _theme = ss.get("theme", "light")
    tab1, tab2, tab3, tab4 = st.tabs(["外观", "模型服务", "数据与隐私", "高级设置"])

    # ---------- 外观 ----------
    with tab1:
        st.html('<div class="fm-sec-title">主题模式</div>')
        _cur = "暗色" if _theme == "dark" else "亮色"
        _mode = st.segmented_control("主题模式", ["亮色", "暗色"], default=_cur,
                                     key="theme_seg")
        if _mode and _mode != _cur:
            ss["theme"] = "dark" if _mode == "暗色" else "light"
            st.query_params["theme"] = ss["theme"]
            st.rerun()
        st.caption("切换后立即生效，刷新页面仍会保持当前选择。")

    # ---------- 模型服务 ----------
    with tab2:
        _prov = st.selectbox("服务商", list(_MODEL_PROVIDERS), key="cfg_provider")
        _d_url, _d_model, _d_key = _MODEL_PROVIDERS[_prov]
        _url = st.text_input("接口地址", value=_d_url, key=f"cfg_base_{_prov}")
        _model = st.text_input("模型名称", value=_d_model, key=f"cfg_model_{_prov}")
        _env_key = os.getenv("LLM_API_KEY", "") or _d_key or ""
        st.text_input("API Key", value=_mask_key(_env_key), disabled=True,
                      key="cfg_key_masked")
        _key = st.text_input("更新 API Key", value="", type="password",
                             placeholder="留空表示沿用已配置的密钥",
                             key=f"cfg_key_{_prov}")
        _b1, _b2 = st.columns(2)
        with _b1:
            if st.button("测试连接", key="cfg_test", use_container_width=True):
                _ok, _msg = _test_llm(_url.strip() or _d_url,
                                      _key.strip() or _env_key)
                ss["_llm_test"] = (bool(_ok), _msg)
        with _b2:
            if st.button("保存配置", key="cfg_save", type="primary", use_container_width=True):
                os.environ["LLM_BASE_URL"] = _url.strip() or _d_url
                os.environ["LLM_MODEL"] = _model.strip() or _d_model
                if _key.strip():
                    os.environ["LLM_API_KEY"] = _key.strip()
                elif _d_key and not _d_key.startswith("sk-REPLACE"):
                    os.environ["LLM_API_KEY"] = _d_key
                st.success("模型配置已保存，下一次对话生效。")
                st.toast("模型配置已保存")
        if ss.get("_llm_test"):
            _ok, _msg = ss["_llm_test"]
            (st.success if _ok else st.error)(f"连接状态：{_msg}")
        else:
            st.caption(f"连接状态：{'已配置密钥' if _env_key and not _env_key.startswith('sk-REPLACE') else '未配置密钥'}")

    # ---------- 数据与隐私 ----------
    with tab3:
        try:
            _db_size = db.DB_PATH.stat().st_size / 1024 / 1024
        except OSError:
            _db_size = 0.0
        _file_count = len(db.list_files(limit=100000))
        st.html(
            '<div class="fm-list-item"><div class="fm-li-t">本地存储</div>'
            f'<div class="fm-li-s">SQLite 数据库 · {_db_size:.2f} MB · 已保存资料 {_file_count} 份</div></div>'
            '<div class="fm-list-item"><div class="fm-li-t">学生数据隔离</div>'
            '<div class="fm-li-s">学生空间只能看到本人答疑、教师已发布的实训与反馈；'
            "教师可见资料不会出现在学生界面。</div></div>"
            '<div class="fm-list-item"><div class="fm-li-t">数据位置</div>'
            '<div class="fm-li-s">全部数据保存在本机 .data 目录，不上传第三方服务。</div></div>'
        )
        _confirm = st.checkbox("我确认清理本地上传副本（数据库中的原始文件不受影响）",
                               key="clean_uploads_ok")
        if st.button("清理本地上传副本", key="clean_uploads", disabled=not _confirm):
            _n = 0
            for _p in UPLOAD_DIR.glob("*"):
                if _p.is_file():
                    try:
                        _p.unlink()
                        _n += 1
                    except OSError:
                        pass
            st.success(f"已清理 {_n} 个本地副本文件。")

    # ---------- 高级设置 ----------
    with tab4:
        with st.expander("高级设置", expanded=False):
            _api_key = os.getenv("LLM_API_KEY", LLM_API_KEY) or ""
            rows = [
                ("接口地址", os.getenv("LLM_BASE_URL", LLM_BASE_URL)),
                ("文件解析器", f"智谱 file-parser · {PARSER_TOOL_TYPE}"
                 + ("" if ZHIPU_API_KEY else " · 未配置 ZHIPU_API_KEY")),
                ("数据库类型", "SQLite（本地单文件）"),
                ("数据库路径", str(db.DB_PATH)),
                ("上传目录", str(UPLOAD_DIR)),
                ("密钥状态", "已配置" if _api_key and not _api_key.startswith("sk-REPLACE") else "未配置"),
            ]
            st.html("".join(
                f'<div class="fm-list-item"><div class="fm-li-t" style="width:104px">{k}</div>'
                f'<div class="fm-li-s" style="overflow-wrap:break-word">{_path_html(v)}</div></div>'
                for k, v in rows
            ))
            st.caption("密钥仅保存在当前进程内存，不写入磁盘；文件内容与任务记录持久保存在 SQLite 数据库中。")


def render_placeholder(title: str, desc: str) -> None:
    with st.container(key="panel"):
        st.html(
            f'<div class="fm-cardhead"><h2>{_esc(title)}</h2><div class="r">规划中</div></div>'
            f'<div class="fm-empty">{_esc(desc)}</div>'
        )


# ---------------------------------------------------------------------------
# 视图路由
# ---------------------------------------------------------------------------
# 主题标记：只用于 CSS 命中浅色/深色 token，本身不占布局
st.markdown(f'<div class="fm-thememode {ss.get("theme", "light")}"></div>', unsafe_allow_html=True)

# Enter 提交绑定：放在视图渲染之前，保证组件 iframe 位于页面顶部可见区域
_bind_enter_submit()



def _render_media_tools() -> None:
    """教学素材页：网络搜索 + 图像生成 + 视频生成（智谱媒体三件套）。"""
    st.html('<div class="fm-page-title">教学素材</div>'
            '<div class="fm-page-sub">网络搜索 · 图像生成 · 视频生成，全部走智谱 AI 原生接口</div>')
    tab_search, tab_image, tab_video = st.tabs(["🔍 网络搜索", "🖼️ 图像生成", "🎬 视频生成"])

    with tab_search:
        st.caption("智谱 Web Search API：增强意图识别，返回结构化结果。支持联网引用、关键词改写、多搜索引擎切换。")
        c1, c2, c3, c4, c5 = st.columns([3, 1.2, 1.2, 1.2, 1.2], gap="small")
        with c1:
            q = st.text_input("搜索关键词", key="ws_query", placeholder="如「2025年高中数学新课标变化」", label_visibility="collapsed")
        with c2:
            engine = st.selectbox("引擎", ["search_std", "search_pro", "search_pro_sogou", "search_pro_quark"],
                                  format_func=lambda x: {"search_std": "基础版", "search_pro": "高阶版",
                                                         "search_pro_sogou": "搜狗", "search_pro_quark": "夸克"}[x],
                                  key="ws_engine")
        with c3:
            count = st.number_input("数量", min_value=1, max_value=50, value=10, step=5, key="ws_count")
        with c4:
            recency = st.selectbox("时间", ["noLimit", "oneDay", "oneWeek", "oneMonth", "oneYear"],
                                   format_func=lambda x: {"noLimit": "不限", "oneDay": "一天内", "oneWeek": "一周内",
                                                          "oneMonth": "一月内", "oneYear": "一年内"}[x],
                                   key="ws_recency")
        with c5:
            intent = st.toggle("意图识别", value=True, key="ws_intent", help="开启后 AI 先判断是否有搜索意图")
        c6, c7 = st.columns([2, 1], gap="small")
        with c6:
            domain = st.text_input("限定域名（可选）", key="ws_domain", placeholder="如 www.gov.cn", label_visibility="collapsed")
        with c7:
            size = st.selectbox("内容长度", ["medium", "high"],
                                format_func=lambda x: "摘要（medium）" if x == "medium" else "详细（high）", key="ws_size")
        if st.button("🔎 开始搜索", key="ws_run", type="primary", use_container_width=True) and q.strip():
            with st.spinner("联网搜索中…"):
                res = _zhipu_web_search(
                    query=q.strip(), search_engine=engine, search_intent=intent,
                    count=int(count), recency_filter=recency, content_size=size,
                    domain_filter=domain.strip() if domain.strip() else None,
                )
            if res.get("status") != "ok":
                st.error(res.get("error", "搜索失败"))
            else:
                ss["ws_last"] = res
                ss["ws_last_query"] = q.strip()
        res = ss.get("ws_last")
        if res and ss.get("ws_last_query"):
            with st.expander(f"📋 搜索结果 · {ss['ws_last_query']}（{res.get('count', 0)} 条，{res.get('elapsed_s', 0):.1f}s）", expanded=True):
                intent_info = res.get("intent") or []
                if intent_info:
                    first = intent_info[0]
                    st.caption(f"意图: **{first.get('intent', '')}** · 改写关键词: `{first.get('keywords', '')}`")
                if res.get("note"):
                    st.info(res["note"])
                for i, r in enumerate(res.get("results", []), 1):
                    with st.container(border=True):
                        c_t, c_m = st.columns([5, 1])
                        with c_t:
                            st.markdown(f"**{i}. [{r['title'] or '(无标题)'}]({r['link']})**")
                        with c_m:
                            st.caption(f"{r.get('media', '') or r.get('icon', '')} · {r.get('publish_date', '')}")
                        if r.get("content"):
                            st.write(r["content"][:300] + ("…" if len(r["content"]) > 300 else ""))

    with tab_image:
        st.caption("智谱图像生成：支持 glm-image-plus / glm-image / cogview-4 / cogview-3。异步提交，轮询等结果。")
        c1, c2, c3 = st.columns([4, 2, 2], gap="small")
        with c1:
            img_prompt = st.text_area("描述", key="img_prompt", height=80,
                                      placeholder="如：手绘风格，一位老师在黑板前讲解函数图像，旁边学生积极举手",
                                      label_visibility="collapsed")
        with c2:
            img_model = st.selectbox("模型", list(zhipu_media.IMAGE_MODELS.keys()),
                                     format_func=lambda x: f"{x} · {zhipu_media.IMAGE_MODELS[x]}", key="img_model")
        with c3:
            img_size = st.selectbox("尺寸", ["1024x1024", "1280x720", "720x1280", "2048x2048"], key="img_size")
        if st.button("🖼️ 生成图片", key="img_run", type="primary", use_container_width=True) and img_prompt.strip():
            with st.spinner("生成中（约 10-60s）…"):
                res = zhipu_media.generate_image(
                    prompt=img_prompt.strip(), model=img_model, size=img_size, num=1,
                    poll=True, max_wait=180,
                )
            if res.get("status") != "ok":
                st.error(res.get("error", "图像生成失败"))
            else:
                ss["img_last"] = res
        img_res = ss.get("img_last")
        if img_res:
            st.caption(f"模型: {img_res.get('model', '')} · 任务ID: `{img_res.get('task_id', '')}`")
            for item in img_res.get("images", []):
                url = item.get("url", "")
                if url:
                    st.image(url, use_container_width=True)
                    st.markdown(f"[原图链接]({url})")

    with tab_video:
        st.caption("智谱视频生成：glm-video-plus / glm-video / cogvideox。生成较慢，建议 5-10 分钟等待。")
        c1, c2, c3 = st.columns([4, 2, 1.5], gap="small")
        with c1:
            vid_prompt = st.text_area("描述", key="vid_prompt", height=80,
                                      placeholder="如：一段 5 秒的教学短视频，展示化学反应中颜色变化的特写镜头",
                                      label_visibility="collapsed")
        with c2:
            vid_model = st.selectbox("模型", list(zhipu_media.VIDEO_MODELS.keys()),
                                     format_func=lambda x: f"{x} · {zhipu_media.VIDEO_MODELS[x]}", key="vid_model")
        with c3:
            vid_dur = st.number_input("时长(秒)", min_value=5, max_value=15, value=5, step=5, key="vid_dur")
        if st.button("🎬 生成视频", key="vid_run", type="primary", use_container_width=True) and vid_prompt.strip():
            with st.spinner("视频生成中（可能需要几分钟）…"):
                res = zhipu_media.generate_video(
                    prompt=vid_prompt.strip(), model=vid_model,
                    duration=int(vid_dur), poll=True, max_wait=600,
                )
            if res.get("status") != "ok":
                st.error(res.get("error", "视频生成失败"))
            else:
                ss["vid_last"] = res
        vid_res = ss.get("vid_last")
        if vid_res:
            st.caption(f"模型: {vid_res.get('model', '')} · 任务ID: `{vid_res.get('task_id', '')}`")
            for item in vid_res.get("videos", []):
                vurl = item.get("url", "")
                cover = item.get("cover", "")
                if cover:
                    st.image(cover, caption="封面", use_container_width=True)
                if vurl:
                    st.video(vurl)
                    st.markdown(f"[视频链接]({vurl})")


if edu_ui.is_student_mode() and VIEW in _TEACHER_VIEWS:
    st.html('<div class="fm-empty">学生空间不含该功能。需要备课、实训、评审或学情分析，'
            "请在顶部切换到教师工作台。</div>")
    if st.button("返回学生首页", key="back_student_home", type="primary"):
        ss.nav = "首页"
        st.rerun()
elif VIEW == "首页":
    render_hero()
elif VIEW == "AI 助手":
    _task_banner("AI 助手")
    render_ai_page(auto_start=bool(ss.pop("auto_run", False)))
elif VIEW == "我的任务":
    edu_ui.render_student_tasks_page()
elif VIEW == "教师反馈":
    edu_ui.render_student_feedback_page()
elif VIEW == "错题回顾":
    edu_ui.render_student_wrong_page()
elif VIEW == "教学素材":
    _render_media_tools()
elif VIEW == "教学工具":
    _task_banner("教学工具")
    # 该页不展示卡片：文件直接拖到下方胶囊输入栏即可上传
    if ss.get("queued_prompt"):
        st.html('<div class="fm-empty" style="padding:0 0 8px">任务已暂停：'
                f'{_esc(ss.queued_prompt)}<br>上传文件成功后会自动继续执行。</div>')
    _bind_drop_upload()
    # 上传完成 → 继续执行排队中的任务
    if ss.get("queued_prompt") and _has_data():
        ss.auto_run = True
        ss.queued_prompt = None
    # 「数据概览 / 报告工坊」不常驻：仅当用户提出分析数据 / 生成报告的需求时才出现
    _last_q = (ss.get("pending_q") or "").strip()
    if not _last_q:
        for _msg in reversed(ss.chat_history):
            if _msg.get("role") == "user":
                _last_q = (_msg.get("text") or "").strip()
                break
    _need_analysis = any(k in _last_q for k in ("分析", "统计", "汇总", "计算", "趋势",
                                                "对比", "占比", "平均", "合计", "总计"))
    _need_report = any(k in _last_q for k in ("报告", "周报", "月报", "汇报"))
    if _need_analysis and _need_report:
        _tab_data, _tab_report = st.tabs(["数据概览", "报告工坊"])
        with _tab_data:
            _excel_analysis_block()
        with _tab_report:
            _excel_report_block()
    elif _need_analysis:
        _excel_analysis_block()
    elif _need_report:
        _excel_report_block()
    render_chat(with_header=True, auto_start=bool(ss.pop("auto_run", False)))
elif VIEW == "课程项目":
    edu_ui.render_course_page()
elif VIEW == "一键备课":
    edu_ui.render_lesson_page()
elif VIEW == "创建实训":
    edu_ui.render_training_page()
elif VIEW == "学生答疑":
    edu_ui.render_tutor_page()
elif VIEW == "作业评审":
    edu_ui.render_review_page()
elif VIEW == "学情分析":
    edu_ui.render_analytics_page()
elif VIEW == "文件":
    render_files_page()
    _sync_parse_panel()
elif VIEW == "任务":
    render_tasks_page()
elif VIEW == "设置":
    render_settings()
else:
    render_placeholder(VIEW, "该模块尚未实现。")
