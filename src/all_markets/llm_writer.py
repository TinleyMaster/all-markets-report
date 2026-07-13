from __future__ import annotations

from openai import OpenAI

from .report import ReportBundle


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
4. 维持以下结构：标题、今日一句话、四分法结论、资金流向地图、为什么其他市场跌、宏观因子、全球基准表现、主题表现、跨资产表现。
5. “为什么其他市场跌”中的每一条都要带一行逻辑解释。

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

    return ReportBundle(
        date_label=bundle.date_label,
        title=bundle.title,
        short_text=bundle.short_text,
        markdown=polished,
        payload={**bundle.payload, "markdown_polished": polished},
    )
