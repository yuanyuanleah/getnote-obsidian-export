#!/usr/bin/env python3
"""Import Get 笔记 notes or subscription transcripts as local Markdown."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from getnote_source import (
    ConnectionBlocked, ReadError, SourceItem, blogger_detail, blogger_order, blogger_scope,
    cli_image, note_detail, note_scope, string_id, timestamp,
)

DEFAULT_TITLE = "{主题}｜{类型}｜{关键词}"
TITLE_FIELDS = {"日期", "原题", "主题", "类型", "关键词", "博主", "ID"}
OPERATIONS = ("获客", "账号运营", "起号", "变现", "引流", "涨粉", "投放", "转化率", "客单价", "成交", "商业")
COPYWRITING = ("文案", "口播", "爆款", "开头", "脚本", "标题")
REVIEW_MARKER = re.compile(r"\[UNK\]|\*{3,}|【(?:未识别|听不清|无法识别)[^】]*】|\[(?:未识别|听不清|无法识别)[^\]]*\]", re.I)
INDEX_MARKER = "<!-- getnote-obsidian:index:v1 -->"
INDEX_NAMES = {"notes": "00-普通笔记导入索引.md", "bloggers": "00-订阅博主导入索引.md"}


def parse_date(value: str, end: bool = False) -> date:
    value = value.replace(".", "-").replace("/", "-")
    match = re.fullmatch(r"(\d{4})-(\d{1,2})(?:-(\d{1,2}))?", value)
    if not match:
        raise ValueError(f"日期格式无法识别：{value}。用 YYYY-MM 或 YYYY-MM-DD。")
    year, month = int(match[1]), int(match[2])
    if match[3]:
        day = date(year, month, int(match[3]))
        return day + timedelta(days=1) if end else day
    month_start = date(year, month, 1)
    return date(year + (month == 12), month % 12 + 1, 1) if end else month_start


def date_range(args, zone) -> tuple[datetime, datetime]:
    if args.range and (args.from_date or args.to_date):
        raise ValueError("请选择区间写法或分别指定起止日期。")
    if args.range:
        match = re.fullmatch(
            r"\s*(\d{4}[./-]\d{1,2}(?:[./-]\d{1,2})?)\s*(?:至|到|~|～|—|–|-)\s*"
            r"(\d{4}[./-]\d{1,2}(?:[./-]\d{1,2})?)\s*", args.range,
        )
        if not match:
            raise ValueError("日期区间无法识别，例如 2026.10-2026.12。")
        first, last = parse_date(match[1]), parse_date(match[2], end=True)
    elif args.from_date or args.to_date:
        if not (args.from_date and args.to_date):
            raise ValueError("分别填写时，需要同时指定起止日期。")
        first, last = parse_date(args.from_date), parse_date(args.to_date, end=True)
    else:
        month = datetime.now(zone).strftime("%Y-%m")
        first, last = parse_date(month), parse_date(month, end=True)
    if first >= last:
        raise ValueError(f"开始日期晚于结束日期：{first}。")
    return (
        datetime.combine(first, time.min, zone).astimezone(zone),
        datetime.combine(last, time.min, zone).astimezone(zone),
    )


def output_root(args) -> Path:
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        raise ValueError(f"工作区不是现有文件夹：{workspace}")
    explicit = Path(args.output).expanduser() if args.output else None
    if explicit is not None:
        return (workspace / explicit).resolve()
    vault = next((p for p in (workspace, *workspace.parents) if (p / ".obsidian").is_dir()), workspace)
    return vault / "Get笔记导入" / ("普通笔记" if args.mode == "notes" else "订阅博主")


def title_template(value: str) -> str:
    if value == "原题":
        return "{原题}"
    fields = re.findall(r"\{([^{}]*)\}", value)
    remainder = re.sub(r"\{[^{}]*\}", "", value)
    if not fields or set(fields) - TITLE_FIELDS or "{" in remainder or "}" in remainder:
        raise ValueError("标题可用 {日期}、{原题}、{主题}、{类型}、{关键词}、{博主}、{ID}。")
    return value


def compact(value: str) -> str:
    return " ".join(value.split())


def clean_title(value: str) -> str:
    return compact(re.sub(r"(?:^|\s)#[\w\-\u3400-\u9fff]+(?=\s|#|$)", " ", value)).strip("｜-| ")


def title_phrase(value: str, limit: int) -> str:
    line = next((row.strip() for row in value.splitlines() if row.strip()), "")
    line = re.sub(r"^#{1,6}\s*|^[>*\-\s]+", "", line)
    return re.split(r"[。！？!?]", compact(line), maxsplit=1)[0].strip(" ：:，,")[:limit]


def note_labels(title: str, body: str, tags: list[str], default_type: str) -> tuple[str, str, str]:
    # 沿用旧版的标题三段式和运营／素材分类，使用本次数据里的主题和关键词。
    head = clean_title(title)
    if re.fullmatch(r"未命名(?:笔记)?(?:[-－ ]\d+)?", head):
        head = ""
    known = title_phrase(head, 24)
    context = f"{head}\n{' '.join(tags)}\n{body[:2800]}"
    book = re.search(r"《([^》\n]{2,48})》", context)
    operations = [term for term in OPERATIONS if term in context]
    copywriting = [term for term in COPYWRITING if term in context]
    subject = known or (book[1] if book else title_phrase(body, 24)) or "未命名素材"
    if operations and len(operations) > len(copywriting) + bool(book):
        category = "运营类·获客技巧" if "获客" in operations else "运营类·账号运营"
        if "变现" in operations or "商业" in operations:
            category = "运营类·变现方法" if "获客" not in operations else category
    elif default_type == "逐字稿":
        category = "素材类·逐字稿"
    elif book:
        category = "素材类·讲书" if any(x in context for x in ("讲书", "读书", "解读", "推荐")) else "素材类·书摘"
    elif copywriting:
        category = "素材类·文案"
    else:
        category = "素材类·一般笔记"
    keyword = (book[1] if book else next(iter(tags or operations or copywriting), "")) or "待分类"
    return subject[:24], category, compact(keyword)[:18]


def file_part(value: str, budget: int) -> str:
    value = unicodedata.normalize("NFC", value)
    value = re.sub(r'[\\/:*?"<>|\[\]#^\x00-\x1f]', "-", compact(value)).strip(" .-")
    value = value.encode("utf-8")[:budget].decode("utf-8", errors="ignore").rstrip(" .-")
    if not value:
        return "未命名"
    device = re.fullmatch(r"(?i)(con|nul|aux|prn|com[1-9]|lpt[1-9])(?:\..*)?", value)
    return "_" + value if device else value


def note_contents(note: dict) -> dict:
    note_type = str(note.get("note_type") or "")
    audio = note.get("audio") or {}
    webpage = note.get("web_page") or {}
    content = note.get("content") or ""
    quote_text = ""
    summary = ""
    if note_type in {"audio", "meeting", "local_audio", "internal_record", "recorder_audio", "recorder_flash_audio", "class_audio"}:
        raw = audio.get("transcript") or ""
        summary = audio.get("original") or content
    elif note_type == "link":
        raw = webpage.get("original") or webpage.get("original_content") or ""
        summary = webpage.get("content") or content
    else:
        raw = content
        if note_type == "ref":
            quote_text = note.get("ref_content") or ""
    tags = [v if isinstance(v, str) else v.get("name", "") for v in (note.get("tags") or []) if isinstance(v, (str, dict))]
    return {
        "title_raw": str(note.get("title") or ""),
        "original": str(raw),
        "quote": str(quote_text),
        "summary": str(summary),
        "tags": [t for t in tags if isinstance(t, str) and t.strip()],
        "url": str(note.get("note_url") or webpage.get("url") or ""),
        "note_type": note_type,
    }


def blog_contents(post: dict) -> dict:
    title = post.get("post_name") or post.get("post_title") or ""
    return {
        "title_raw": str(post.get("post_name") or ""),
        "source_display_title": str(title),
        "original": str(post.get("post_media_text") or ""),
        "quote": "",
        "summary": str(post.get("post_summary") or ""),
        "tags": [],
        "url": str(post.get("post_url") or ""),
        "note_type": "video",
    }


def render(item, contents: dict, mode: str, template: str, zone, details: dict) -> tuple[dict, str]:
    raw = contents["original"] if contents["original"].strip() else ""
    source_title = contents.get("source_display_title", contents["title_raw"])
    tags = contents["tags"]
    date_value = item.created_at
    if mode == "bloggers" and not date_value:
        date_value = timestamp(details.get("post_publish_time") or details.get("post_create_time"), zone)
    topic, category, keyword = note_labels(
        source_title, raw or contents["quote"] or contents["summary"], tags,
        "逐字稿" if mode == "bloggers" else "笔记",
    )
    fields = {
        "日期": date_value.date().isoformat() if date_value else "日期未知",
        "原题": compact(source_title) or topic,
        "主题": topic,
        "类型": category,
        "关键词": keyword,
        "博主": item.blogger or "普通笔记",
        "ID": item.source_id,
    }
    display = compact(template.format_map(fields))
    metadata = {
        "source_id": item.source_id,
        "source_type": "blogger_content" if mode == "bloggers" else "note",
        "source_url": contents["url"] or (f"https://biji.com/note/{item.source_id}" if mode == "notes" else ""),
        "source_created_at": date_value.isoformat() if date_value else "",
        "source_updated_at": str(details.get("updated_at") or ""),
        "source_tags": tags,
        "source_note_type": contents["note_type"],
        "import_status": "imported" if raw or contents["quote"].strip() else "summary_only",
        "title_raw": contents["title_raw"],
        "title_display": display,
        "primary_subject": topic,
        "material_kind": category,
        "keywords": [keyword],
        "classification_status": "auto_classified" if keyword != "待分类" else "needs_review",
        "privacy": "private",
        "allow_for_content": False,
        "evidence_status": "unverified",
    }
    if item.blogger:
        metadata.update(account_name=item.blogger, source_topic=item.topic_name, source_account_key=item.account_key)
    front = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in metadata.items())
    document = f"---\n{front}\n---\n\n# {display}"
    if raw:
        heading = "视频转写原文" if item.blogger else "原始内容"
        document += f"\n\n## {heading}\n\n{raw}"
    if contents["quote"]:
        document += f"\n\n## 笔记引用的摘录\n\n{contents['quote']}"
    if item.blogger:
        markers = list(dict.fromkeys(REVIEW_MARKER.findall(raw)))
        status = "发现待回看标记：" + "、".join(markers) if markers else "未发现明确缺词标记，专有名词和同音字仍以原视频核对。"
        document += f"\n\n## 转写待核对\n\n{status}"
    if contents["summary"]:
        answer_heading = "Get 摘要" if raw else "Get 已保存的摘要（正文未返回）"
        document += f"\n\n## {answer_heading}\n\n{contents['summary']}"
    return metadata, document + "\n"


def imported_files(root: Path, mode: str) -> dict:
    files = {}
    for path in sorted(root.rglob("*.md")):
        if path.is_symlink() or path.name in INDEX_NAMES.values():
            continue
        path.resolve().relative_to(root)
        with path.open(encoding="utf-8", newline="") as stream:
            start = stream.read(20_000)
        front = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", start, re.S)
        metadata = {}
        if front:
            for field in ("source_id", "source_type", "source_created_at", "title_display", "material_kind", "account_name", "source_account_key", "import_status"):
                match = re.search(rf"^{field}:\s*([^\r\n]+)", front[1], re.M)
                if match:
                    value = match[1].strip()
                    try:
                        metadata[field] = str(json.loads(value)) if value.startswith('"') else value.strip("'")
                    except json.JSONDecodeError:
                        metadata[field] = value
        if mode == "bloggers" and not metadata.get("source_id"):
            original_doc = path.read_text(encoding="utf-8")
            source_section = re.search(r"^## 来源信息\s*\n([\s\S]*?)(?=^## |\Z)", original_doc, re.M)
            if source_section and re.search(r"^## 视频(?:转文字原文稿|转写原文)\s*$", original_doc, re.M):
                legacy = re.search(r"^\s*-\s*Get 笔记内容\s*ID[：:]\s*([A-Za-z0-9_-]+)\s*$", source_section[1], re.M)
                if legacy:
                    metadata.update(source_id=legacy[1], source_type="blogger_content")
        source_type = "note" if mode == "notes" else "blogger_content"
        if metadata.get("source_type") == source_type and metadata.get("source_id"):
            source_id = metadata["source_id"]
            existing = files.get(source_id)
            if existing is None or existing[1].get("import_status") == "summary_only":
                files[source_id] = (path, metadata)
    return files


def write_atomic(path: Path, document: str, *, replace: bool = False) -> None:
    fd, name = tempfile.mkstemp(prefix=".getnote-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(document.encode("utf-8"))
        if replace:
            os.replace(name, path)
        else:
            os.link(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
    if path.read_bytes() != document.encode("utf-8"):
        raise OSError(f"写入回读不一致：{path}")


def index_document(entries: dict, root: Path, mode: str, issues: list[str], total: int, skipped: int, inserted: int) -> str:
    def index_row(entry):
        path, metadata = entry
        return (str(metadata.get("account_name", "")).casefold(), str(metadata.get("source_created_at") or "9999"), path.name)
    def cell(value):
        return str(value).replace("|", r"\|").replace("\n", " ")
    lines = [
        INDEX_MARKER, "# Get 笔记导入索引", "",
        f"本次候选 {total}，新增 {inserted}，已存在 {skipped}，记录的问题 {len(issues)}。",
        "",
        "| 日期 | 标题 | " + ("博主" if mode == "bloggers" else "素材类型") + " |",
        "|---|---|---|",
    ]
    for path, metadata in sorted(entries.values(), key=index_row):
        relative = quote(path.relative_to(root).as_posix(), safe="/")
        label = cell(metadata.get("title_display") or path.stem).replace("[", r"\[").replace("]", r"\]")
        category = cell(metadata.get("account_name" if mode == "bloggers" else "material_kind") or "待整理")
        lines.append(f"| {str(metadata.get('source_created_at') or '未知')[:10]} | [{label}]({relative}) | {category or '待整理'} |")
    if issues:
        lines.extend(["", "## 本次待补读", "", *[f"- {issue}" for issue in issues]])
    return "\n".join(lines) + "\n"


def folder_for(item, metadata: dict, root: Path, entries: dict, groups: dict, mode: str) -> Path:
    if mode == "notes":
        return root / metadata["source_created_at"][:7]
    if item.account_key in groups:
        return groups[item.account_key]
    base = root / file_part(item.blogger, 135)
    owners = {m.get("source_account_key") for p, m in entries.values() if p.parent == base}
    if owners - {None, item.account_key} or base in groups.values():
        digest = hashlib.sha256(item.account_key.encode()).hexdigest()[:8]
        base = root / f"{base.name}-{digest}"
    groups[item.account_key] = base
    return base


def read_staged(path: Path, mode: str, zone, start=None, end=None, *, topic=None, bloggers=()) -> tuple[list[SourceItem], dict]:
    staged = {}
    items = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                detail = row["record"]
                if not isinstance(detail, dict):
                    raise ValueError("record 必须是对象")
                if mode == "notes":
                    source_id = string_id(detail.get("note_id") or detail.get("id"))
                    created = timestamp(detail.get("created_at"), zone)
                    if not created:
                        raise ValueError("缺少创建时间")
                    if not start <= created < end:
                        continue
                    item = SourceItem(source_id, created)
                else:
                    source_id = string_id(detail.get("post_id_alias"))
                    if detail.get("post_type") and str(detail["post_type"]).lower() != "video":
                        continue
                    name, topic_name = str(row["blogger"]).strip(), str(row["topic_name"]).strip()
                    if not name or not topic_name:
                        raise ValueError("缺少博主或知识库名称")
                    topic_id, follow_id = string_id(row["topic_id"]), string_id(row["follow_id"])
                    if topic and topic not in (topic_id, topic_name):
                        continue
                    if bloggers and name not in bloggers and follow_id not in bloggers:
                        continue
                    created = timestamp(detail.get("post_publish_time") or detail.get("post_create_time"), zone)
                    account_key = str(row.get("account_key") or f"{topic_id}:{follow_id}")
                    item = SourceItem(source_id, created, topic_id, topic_name, name, account_key)
            except (KeyError, TypeError, ValueError, ReadError) as exc:
                raise ValueError(f"暂存 JSONL 第 {line_number} 行格式无效。") from exc
            items.setdefault(source_id, item)
            staged.setdefault(source_id, detail)
    if mode == "notes":
        return sorted(items.values(), key=lambda item: (item.created_at, item.source_id)), staged
    return sorted(items.values(), key=blogger_order), staged


def execute(args) -> int:
    zone = ZoneInfo(args.timezone) if args.timezone else None
    root = output_root(args)
    template = title_template(args.title)
    known = imported_files(root, args.mode)
    issues = []
    staged = {}
    command = None if args.records else cli_image(args.cli)
    if args.mode == "notes":
        start, end = date_range(args, zone)
        scope = {"from": start.isoformat(), "to_exclusive": end.isoformat(), "as_of": datetime.now(zone).astimezone(zone).isoformat()}
        if args.records:
            items, staged = read_staged(Path(args.records), args.mode, zone, start, end)
        else:
            items = note_scope(command, start, end, zone)
    else:
        scope = {"knowledge_base": args.knowledge_base or "自有知识库", "bloggers": args.blogger or "全部订阅博主"}
        if args.records:
            items, staged = read_staged(Path(args.records), args.mode, zone, topic=args.knowledge_base, bloggers=args.blogger)
        else:
            items, issues = blogger_scope(command, zone, list(dict.fromkeys(args.blogger)), args.knowledge_base)
    if args.records:
        scope["scope_evidence"] = "仅包含本次暂存的记录，完整性由采集方核对。"
    complete = {source_id for source_id, (_, metadata) in known.items() if metadata.get("import_status") != "summary_only"}
    pending = [item for item in items if item.source_id not in complete]
    report = {"mode": args.mode, "scope": scope, "output": str(root), "found": len(items),
              "existing": len(items) - len(pending)}
    if args.mode == "bloggers":
        report["by_blogger"] = dict(Counter(item.blogger for item in items))
    if args.preview:
        report.update(status="preview", new=len(pending), source_ids=[i.source_id for i in pending], issues=issues)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"找到 {len(items)} 项，需新增 {len(pending)} 项。", file=sys.stderr, flush=True)
    inserted = 0
    saved_summaries = 0
    groups = {m["source_account_key"]: p.parent for p, m in known.values() if m.get("source_account_key")}
    index = root / INDEX_NAMES[args.mode]
    index_exists = index.exists()
    if index.is_symlink() or (index_exists and not index.read_text(encoding="utf-8").startswith(INDEX_MARKER)):
        raise ValueError(f"目标已存在同名索引且不是本技能生成：{index}")
    for number, item in enumerate(pending, 1):
        if number == 1 or number % 20 == 0:
            print(f"正在读取第 {number}/{len(pending)} 项。", file=sys.stderr, flush=True)
        try:
            if args.mode == "notes":
                details = staged[item.source_id] if args.records else note_detail(command, item.source_id)
                contents = note_contents(details)
            else:
                details = staged[item.source_id] if args.records else blogger_detail(command, item)
                contents = blog_contents(details)
            if (args.mode == "bloggers" and not contents["original"].strip()) or not any(
                contents[k].strip() for k in ("original", "quote", "summary")
            ):
                issues.append(f"{item.source_id}：Get 尚未返回可导入的正文或视频转写，下次运行重查。")
                continue
            metadata, document = render(item, contents, args.mode, template, zone, details)
            folder = folder_for(item, metadata, root, known, groups, args.mode)
            if folder.resolve() != folder or not folder.is_relative_to(root):
                raise ValueError(f"目标子目录指向另一位置：{folder}")
            folder.mkdir(parents=True, exist_ok=True)
            prefix = f"GN-{'BLG-' if args.mode == 'bloggers' else ''}{item.source_id}_"
            summary_only = metadata["import_status"] == "summary_only"
            is_known = item.source_id in known
            if summary_only:
                issues.append(f"{item.source_id}：Get 只返回摘要，下次运行会重查原文。")
                if is_known:
                    continue
            suffix = "_摘要待补.md" if summary_only else ".md"
            filename = prefix + file_part(metadata["title_display"], 185 - len(prefix)) + suffix
            path = folder / filename
            write_atomic(path, document)
            known[item.source_id] = (path, metadata)
            if summary_only:
                saved_summaries += 1
            else:
                inserted += 1
        except ConnectionBlocked as exc:
            issues.append(f"{item.source_id}：{exc} 还有 {len(pending)-number} 项未读。")
            break
        except (ReadError, OSError, ValueError) as exc:
            issues.append(f"{item.source_id}：{exc}")
    root.mkdir(parents=True, exist_ok=True)
    known = imported_files(root, args.mode)
    write_atomic(index, index_document(known, root, args.mode, issues, len(items), report["existing"], inserted), replace=index_exists)
    report.update(status="issues" if issues else "completed", inserted=inserted, saved_summaries=saved_summaries, index=str(index), issues=issues)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if issues else 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="将 Get 笔记普通笔记或订阅博主原文导入本地 Markdown。")
    modes = root.add_subparsers(dest="mode", required=True)
    for mode, purpose in (("notes", "按创建日期导入普通笔记"), ("bloggers", "导入订阅博主逐字稿")):
        command = modes.add_parser(mode, help=purpose)
        command.add_argument("--workspace", default=".", help="当前工作区或 Vault")
        command.add_argument("--output", help="自定义保存目录，可用相对路径")
        command.add_argument("--title", default=DEFAULT_TITLE if mode == "notes" else "原题", help="原题或使用字段的标题模板")
        command.add_argument("--timezone", help="用户时区，例如 Asia/Shanghai，省略时用本机时区")
        command.add_argument("--preview", action="store_true", help="显示范围和新增候选，不写入目标")
        source = command.add_mutually_exclusive_group()
        source.add_argument("--cli", help="官方 getnote CLI 路径，默认从当前会话 PATH 查找")
        source.add_argument("--records", help="当前客户端通过 Get 连接器读取的本地临时 JSONL")
    notes = modes.choices["notes"]
    notes.add_argument("--range", help="包含两端的月份或日期区间，例如 2026.10-2026.12")
    notes.add_argument("--from", dest="from_date", help="起始月份或日期，包含")
    notes.add_argument("--to", dest="to_date", help="结束月份或日期，包含")
    bloggers = modes.choices["bloggers"]
    bloggers.add_argument("--knowledge-base", help="自有知识库名称或 ID")
    bloggers.add_argument("--blogger", action="append", default=[], help="订阅博主名称或 ID，可重复")
    return root


def main() -> int:
    try:
        return execute(parser().parse_args())
    except (ReadError, OSError, ValueError, ZoneInfoNotFoundError) as exc:
        print(f"导入停止：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
