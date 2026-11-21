"""Read-only access to Get 笔记 through the authenticated official CLI."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import NamedTuple


class ReadError(RuntimeError):
    pass


class ConnectionBlocked(ReadError):
    pass


class SourceItem(NamedTuple):
    source_id: str
    created_at: datetime | None
    topic_id: str = ""
    topic_name: str = ""
    blogger: str = ""
    account_key: str = ""


def string_id(value: object) -> str:
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        identifier = str(value)
        if re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,127}", identifier):
            return identifier
    raise ReadError("Get 返回了空白或无法识别的 ID。")


def timestamp(value: object, zone) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            seconds = float(value)
            if abs(seconds) >= 100_000_000_000:
                seconds /= 1000
            return datetime.fromtimestamp(seconds, timezone.utc).astimezone(zone)
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.astimezone(zone) if result.tzinfo or zone is None else result.replace(tzinfo=zone)
    except (ValueError, OverflowError, OSError) as exc:
        raise ReadError("Get 返回了无法识别的时间字段。") from exc


def cli_image(executable: str | None) -> str:
    command = shutil.which(executable or "getnote")
    if not command:
        raise ReadError("当前 AI 会话找不到官方 getnote CLI。请引导用户安装并完成浏览器授权。")
    return command


def invoke(command: str, args: list[str], timeout: int = 90):
    try:
        return subprocess.run(
            [command, *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ReadError(f"Get 读取超时（{args[0]}），已完成的文件可在续跑时跳过。") from exc
    except OSError as exc:
        raise ReadError(f"无法启动 getnote CLI（{exc.strerror}）。") from exc


def payload(command: str, *args: str, timeout: int = 90) -> dict:
    result = invoke(command, [*args, "-o", "json"], timeout)
    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError:
        envelope = {}
    if not isinstance(envelope, dict):
        raise ReadError(f"CLI 返回了不支持的结果格式（{args[0]}）。")
    if result.returncode or envelope.get("success") is False:
        error = envelope.get("error")
        error = error if isinstance(error, dict) else {}
        code = error.get("code", "")
        reason = str(error.get("reason", "")) + " " + result.stderr.casefold()
        if code in (401, 403, 10201, "401", "403", "10201") or any(
            hint in reason for hint in ("unauthorized", "permission denied", "api key", "not_member", "未登录", "授权")
        ):
            raise ConnectionBlocked("账号授权、额度或权限需要检查。请用官方 CLI 诊断，凭证留在本机。")
        if code in (429, 10202, "429", "10202") or any(
            hint in reason for hint in ("rate_limit", "too many requests", "quota", "限流", "额度")
        ):
            raise ConnectionBlocked("Get 返回限流或额度不足。已写入的文件保留，下次重跑将跳过已导入项。")
        safe_code = f"，错误码 {code}" if str(code).isdigit() else ""
        raise ReadError(f"Get CLI 读取失败（{args[0]}{safe_code}）。")
    values = envelope.get("data")
    if not isinstance(values, dict):
        raise ReadError(f"CLI 返回缺少 data（{args[0]}）。")
    return values


def rows(values: dict, key: str) -> list[dict]:
    if values.get("partial") or values.get("warnings"):
        raise ReadError(f"{key} 列表覆盖不完整，已保留既有文件。")
    records = values.get(key)
    if key in values and records is None:
        return []
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise ReadError(f"Get 返回缺少可读的 {key} 列表。")
    return records


def pages(command: str, key: str, *args: str):
    previous_pages = set()
    page = 1
    while True:
        values = payload(command, *args, "--page", str(page))
        batch = rows(values, key)
        more = values.get("has_more")
        if not isinstance(more, bool):
            raise ReadError(f"Get 没有说明 {key} 是否还有下一页。")
        signature = json.dumps(batch, sort_keys=True, ensure_ascii=False)
        if (more and not batch) or (batch and signature in previous_pages):
            raise ReadError(f"{key} 翻页没有前进，第 {page} 页无法核对。")
        yield from batch
        if not more:
            return
        previous_pages.add(signature)
        page += 1


def note_rows(command: str, start: datetime, end: datetime):
    help_result = invoke(command, ["notes", "--help"], 15)
    if help_result.returncode:
        raise ReadError("无法检查 getnote notes 命令。")
    if "--created-from" in help_result.stdout and "--created-to" in help_result.stdout:
        values = payload(
            command, "notes", "--all", "--created-from", start.isoformat(),
            "--created-to", end.isoformat(), timeout=900,
        )
        records = rows(values, "notes")
        traversal = values.get("traversal") or {}
        if values.get("has_more") is not False or (traversal and traversal.get("completed") is not True):
            raise ReadError("普通笔记遍历未完成，不能交付为全量。")
        yield from records
        return

    # 支持旧 CLI：逐页在本机筛日期，范围外的笔记不请求详情。
    print("当前 CLI 使用游标遍历，日期范围在本机筛选。", file=sys.stderr, flush=True)
    visited = set()
    args = []
    while True:
        values = payload(command, "notes", *args)
        yield from rows(values, "notes")
        more = values.get("has_more")
        if more is False:
            return
        cursor = str(values.get("cursor") or values.get("next_cursor") or "")
        if more is not True or not cursor or cursor in visited:
            raise ReadError("普通笔记翻页缺少有效游标，不能交付为全量。")
        visited.add(cursor)
        args = ["--cursor", cursor]


def note_scope(command: str, start: datetime, end: datetime, zone) -> list[SourceItem]:
    selected = {}
    for row in note_rows(command, start, end):
        source_id = string_id(row.get("note_id") or row.get("id"))
        created = timestamp(row.get("created_at"), zone)
        if created is None:
            raise ReadError(f"笔记 {source_id} 缺少创建时间，无法核对导入范围。")
        if start <= created < end:
            selected[source_id] = SourceItem(source_id, created)
    return sorted(selected.values(), key=lambda item: (item.created_at, item.source_id))


def blogger_scope(command: str, zone, names: list[str], wanted_topic: str | None) -> tuple[list[SourceItem], list[str]]:
    topics = list(pages(command, "topics", "kbs"))
    if wanted_topic:
        matches = [t for t in topics if wanted_topic in (t.get("topic_id"), t.get("name"))]
        if len(matches) != 1:
            raise ReadError("没有唯一匹配的自有知识库，请提供准确名称或 ID。")
        topics = matches
    selected = {}
    found = set()
    account_seen = set()
    for topic in topics:
        topic_id = string_id(topic.get("topic_id"))
        for blogger in pages(command, "bloggers", "kb", "bloggers", topic_id):
            name = str(blogger.get("account_name") or "").strip()
            follow_id = string_id(blogger.get("follow_id_str") or blogger.get("follow_id"))
            matching = set(names).intersection({name, follow_id})
            if names and not matching:
                continue
            found.update(matching)
            account_key = str(blogger.get("follow_link") or f"{blogger.get('platform') or ''}:{name or follow_id}")
            if account_key not in account_seen:
                account_seen.add(account_key)
                print(f"正在读取订阅博主（已找到 {len(account_seen)} 位）。", file=sys.stderr, flush=True)
            for row in pages(command, "contents", "kb", "blogger-contents", topic_id, follow_id):
                if row.get("post_type") and str(row["post_type"]).lower() != "video":
                    continue
                source_id = string_id(row.get("post_id_alias"))
                created = timestamp(row.get("post_publish_time") or row.get("post_published_at") or row.get("post_create_time") or row.get("post_created_at") or row.get("publish_time"), zone)
                selected.setdefault(source_id, SourceItem(source_id, created, topic_id, str(topic.get("name") or ""), name or follow_id, account_key))
    missing = [name for name in names if name not in found]
    if not account_seen:
        detail = "找不到这些订阅博主：" + "、".join(missing) if missing else "当前自有知识库未列出订阅博主。"
        raise ReadError(detail + " 请检查 Get 中的订阅范围。")
    return sorted(selected.values(), key=blogger_order), [f"找不到订阅博主：{name}" for name in missing]


def blogger_order(item: SourceItem):
    return (item.blogger.casefold(), item.account_key, item.created_at is None, item.created_at, item.source_id)


def note_detail(command: str, source_id: str) -> dict:
    note = payload(command, "note", source_id).get("note")
    if not isinstance(note, dict) or string_id(note.get("note_id") or note.get("id")) != source_id:
        raise ReadError(f"笔记 {source_id} 详情与来源 ID 不一致。")
    return note


def blogger_detail(command: str, item: SourceItem) -> dict:
    values = payload(command, "kb", "blogger-content", item.topic_id, item.source_id)
    record = values["content"] if isinstance(values.get("content"), dict) else values
    returned_id = record.get("post_id_alias")
    if returned_id and string_id(returned_id) != item.source_id:
        raise ReadError(f"订阅内容 {item.source_id} 详情与来源 ID 不一致。")
    if not any(field in record for field in ("post_name", "post_title", "post_media_text")):
        raise ReadError(f"订阅内容 {item.source_id} 的详情字段缺失。")
    return record
