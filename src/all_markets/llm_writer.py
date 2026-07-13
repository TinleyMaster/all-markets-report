from __future__ import annotations

import re

from openai import OpenAI

from .report import ReportBundle


def _normalize_markdown(markdown: str) -> str:
    text = markdown.strip()
    if not text:
        return markdown

    replacements = {
        r"\|": "|",
        r"\-": "-",
        r"\*": "*",
        r"\.": ".",
        r"\+": "+",
        r"\(": "(",
        r"\)": ")",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    lines = [line.rstrip() for line in text.splitlines()]
    normalized: list[str] = []
    previous_blank = False
    for line in lines:
        current = line.strip()
        if not current:
            if not previous_blank:
                normalized.append("")
            previous_blank = True
            continue

        if (
            current.startswith("> ")
            and len(normalized) >= 2
            and normalized[0].startswith("# ")
        ):
            if normalized[-1] != "":
                normalized.append("")
            normalized.append(current)
            previous_blank = False
            continue

        if current.startswith("|"):
            if (
                normalized
                and normalized[-1] == ""
                and len(normalized) >= 2
                and normalized[-2].startswith("|")
            ):
                normalized.pop()
            normalized.append(current)
            previous_blank = False
            continue

        if re.match(r"^[-*] ", current):
            normalized.append(current)
            previous_blank = False
            continue

        normalized.append(current)
        previous_blank = False

    return "\n".join(normalized).strip()


def polish_report_with_deepseek(
    bundle: ReportBundle, api_key: str, model: str
) -> ReportBundle:
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    prompt = f"""
你是一名机构视角的全球宏观市场策略分析师。请在不捏造数据的前提下，
基于下面这份规则引擎生成的市场日报，润色为更像投研晨报的中文版本。

要求：
1. 保留原始结论方向，不得新增未提供的市场、标的或数字。
2. 语言简洁、有信息密度，避免空话。
3. 输出必须是 Markdown。
4. 必须保留“两层输出”结构：
   - 第1层：日频免费主报告
   - 第2层：周频增强信号
5. 第1层中要保留：四分法结论、股票地域轮动、股票行业轮动、为什么其他市场跌、宏观因子、全球基准表现、主题表现、跨资产表现。
6. 第2层中要保留：CFTC COT、A股北向资金、BTC ETF 净流入、信用债 ETF 风险偏好。若某项为空，不要编造。
7. “为什么其他市场跌”中的每一条都要带一行逻辑解释。
8. 不要转义 Markdown 语法字符，不要输出 `\|`、`\*`、`\-` 这类写法。
9. 表格必须保持标准 Markdown 表格格式，表头、分隔线、数据行之间不要插入空行。

原始 Markdown：
{bundle.markdown}
""".strip()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是严谨的中文宏观策略分析师。"},
            {"role": "user", "content": prompt},
        ],
        stream=False,
    )
    polished = (response.choices[0].message.content or "").strip()
    if not polished:
        return bundle
    polished = _normalize_markdown(polished)

    return ReportBundle(
        date_label=bundle.date_label,
        title=bundle.title,
        short_text=bundle.short_text,
        markdown=polished,
        payload={**bundle.payload, "markdown_polished": polished},
    )
