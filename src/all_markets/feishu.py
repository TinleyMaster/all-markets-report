from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import requests


class FeishuError(RuntimeError):
    """Feishu API request failed."""


@dataclass
class FeishuCredentials:
    app_id: str
    app_secret: str
    document_id: str | None = None


def push_group_message(webhook_url: str, title: str, text: str) -> None:
    response = requests.post(
        webhook_url,
        json={
            "msg_type": "text",
            "content": {"text": f"{title}\n\n{text}"},
        },
        timeout=30,
    )
    response.raise_for_status()


def _request_json(method: str, url: str, **kwargs) -> dict:
    response = requests.request(method=method, url=url, timeout=30, **kwargs)
    response.raise_for_status()
    data = response.json()
    if data.get("code", 0) not in {0, None}:
        raise FeishuError(f"Feishu API error: {data.get('msg') or data}")
    return data


def get_tenant_access_token(credentials: FeishuCredentials) -> str:
    data = _request_json(
        "POST",
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={
            "app_id": credentials.app_id,
            "app_secret": credentials.app_secret,
        },
    )
    token = data.get("tenant_access_token")
    if not token:
        raise FeishuError("未获取到 tenant_access_token")
    return token


def _text_elements(content: str) -> list[dict]:
    return [{"text_run": {"content": content}}]


def markdown_to_blocks(markdown: str) -> list[dict]:
    blocks: list[dict] = []
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("# "):
            blocks.append({"block_type": 3, "heading1": {"elements": _text_elements(line[2:].strip())}})
        elif line.startswith("## "):
            blocks.append({"block_type": 4, "heading2": {"elements": _text_elements(line[3:].strip())}})
        elif line.startswith("### "):
            blocks.append({"block_type": 5, "heading3": {"elements": _text_elements(line[4:].strip())}})
        elif line.startswith("- "):
            blocks.append({"block_type": 12, "bullet": {"elements": _text_elements(line[2:].strip())}})
        else:
            blocks.append({"block_type": 2, "text": {"elements": _text_elements(line)}})
    return blocks


def _chunked(items: Iterable[dict], size: int) -> list[list[dict]]:
    batch: list[dict] = []
    chunks: list[list[dict]] = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            chunks.append(batch)
            batch = []
    if batch:
        chunks.append(batch)
    return chunks


def append_to_document(credentials: FeishuCredentials, markdown: str) -> None:
    if not credentials.document_id:
        raise FeishuError("缺少飞书文档 ID")
    token = get_tenant_access_token(credentials)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    blocks = markdown_to_blocks(markdown)
    for batch in _chunked(blocks, 20):
        _request_json(
            "POST",
            f"https://open.feishu.cn/open-apis/docx/v1/documents/{credentials.document_id}/blocks/{credentials.document_id}/children?document_revision_id=-1",
            headers=headers,
            json={"children": batch, "index": -1},
        )
