from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import requests


class FeishuError(RuntimeError):
    """Feishu API request failed."""


@dataclass
class FeishuCredentials:
    app_id: str
    app_secret: str


@dataclass
class FeishuDocument:
    document_id: str
    title: str
    url: str | None = None


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


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }


def extract_folder_token(folder_ref: str) -> str:
    match = re.search(r"(fld[a-zA-Z0-9]+)", folder_ref)
    return match.group(1) if match else folder_ref.strip()


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
        elif line.startswith("|"):
            blocks.append({"block_type": 2, "text": {"elements": _text_elements(line)}})
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


def _list_folder_items(token: str, folder_token: str) -> list[dict]:
    data = _request_json(
        "GET",
        "https://open.feishu.cn/open-apis/drive/v1/files",
        headers={"Authorization": f"Bearer {token}"},
        params={"folder_token": folder_token, "page_size": 200},
    )
    payload = data.get("data", {})
    return payload.get("files") or payload.get("items") or []


def _find_child_folder(token: str, parent_folder_token: str, folder_name: str) -> str | None:
    for item in _list_folder_items(token, parent_folder_token):
        item_name = item.get("name") or item.get("title")
        item_type = item.get("type") or item.get("file_type")
        item_token = item.get("token") or item.get("file_token")
        if item_name == folder_name and item_type == "folder" and item_token:
            return item_token
    return None


def _create_folder(token: str, parent_folder_token: str, folder_name: str) -> str:
    data = _request_json(
        "POST",
        "https://open.feishu.cn/open-apis/drive/v1/files/create_folder",
        headers=_headers(token),
        json={"name": folder_name, "folder_token": parent_folder_token},
    )
    folder_token = data.get("data", {}).get("token")
    if not folder_token:
        raise FeishuError(f"创建文件夹失败: {folder_name}")
    return folder_token


def get_or_create_child_folder(token: str, parent_folder_token: str, folder_name: str) -> str:
    existed = _find_child_folder(token, parent_folder_token, folder_name)
    if existed:
        return existed
    return _create_folder(token, parent_folder_token, folder_name)


def ensure_archive_folder(token: str, parent_folder_ref: str, report_date: datetime) -> str:
    root_folder = extract_folder_token(parent_folder_ref)
    year_folder = get_or_create_child_folder(token, root_folder, report_date.strftime("%Y"))
    month_folder = get_or_create_child_folder(token, year_folder, report_date.strftime("%m"))
    return month_folder


def create_document(token: str, title: str, folder_token: str) -> FeishuDocument:
    data = _request_json(
        "POST",
        "https://open.feishu.cn/open-apis/docx/v1/documents",
        headers=_headers(token),
        json={"title": title, "folder_token": folder_token},
    )
    document = data.get("data", {}).get("document") or data.get("data") or {}
    document_id = document.get("document_id") or document.get("documentId")
    url = document.get("url")
    if not document_id:
        raise FeishuError("创建飞书云文档失败")
    return FeishuDocument(document_id=document_id, title=title, url=url)


def write_document_markdown(token: str, document_id: str, markdown: str) -> None:
    blocks = markdown_to_blocks(markdown)
    for batch in _chunked(blocks, 20):
        _request_json(
            "POST",
            f"https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/children?document_revision_id=-1",
            headers=_headers(token),
            json={"children": batch, "index": -1},
        )


def create_dated_report_document(
    credentials: FeishuCredentials,
    parent_folder_ref: str,
    report_date: datetime,
    report_brand: str,
    markdown: str,
) -> FeishuDocument:
    token = get_tenant_access_token(credentials)
    archive_folder = ensure_archive_folder(token, parent_folder_ref, report_date)
    doc_title = f"{report_date.strftime('%Y-%m-%d')} {report_brand}.md"
    document = create_document(token, doc_title, archive_folder)
    write_document_markdown(token, document.document_id, markdown)
    if not document.url:
        document.url = f"https://www.feishu.cn/docx/{document.document_id}"
    return document


def send_group_message(
    credentials: FeishuCredentials,
    chat_id: str,
    title: str,
    text: str,
    document: FeishuDocument | None = None,
) -> None:
    token = get_tenant_access_token(credentials)
    body_lines = [title, "", text]
    if document and document.url:
        body_lines.extend(["", f"文档归档：{document.title}", document.url])

    _request_json(
        "POST",
        "https://open.feishu.cn/open-apis/im/v1/messages",
        headers=_headers(token),
        params={"receive_id_type": "chat_id"},
        json={
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": "\n".join(body_lines)}, ensure_ascii=False),
        },
    )
