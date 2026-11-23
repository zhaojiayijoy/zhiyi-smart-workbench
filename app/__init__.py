"""LangChain 数据分析智能体。

核心原则：
1. **不伪造数据**：任何工具都不得返回示例数据 / 模拟结果 / 占位数字。当数据缺失或不可读时，返回包含 missing_fields 的结构化错误，由 Agent 决定如何应对。
2. **强制数据闸门**：进入 LLM 分析前，必须经过 guard 校验；关键列缺失 / 全空 / 类型异常直接中止。
3. **数据可追溯**：所有工具输出附带 provenance（文件、sheet、列名、记录数），最终建议必须标注每个数字的来源。
4. **确定性计算**：所有统计 / 分组 / 聚合用 pandas 完成，LLM 只负责提出分析方向、解释结果、生成文字建议。
5. **受限工具集**：不开放 PythonREPL、shell eval 等任意执行能力。

运行方式：
    streamlit run streamlit_app.py
"""

from __future__ import annotations
