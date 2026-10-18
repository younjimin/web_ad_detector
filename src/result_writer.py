"""result.json 생성기. 스펙: UTF-8(BOM 없음), meta + findings[].
findings 항목 키: id, url, is_violation, location, evidence_text, technique (그 외 키는 넣지 않는다)."""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

TOOL_VERSION = "0.1.0"
TECHNIQUES = ("HOMOGLYPH", "JAMO", "TRANSPARENT", "OFFSCREEN")
DEFAULT_TOPIC = "불법광고"       # TODO: 주최측에 meta.topic 값을 확인할 것


def _iso(dt: datetime) -> str:
    return dt.astimezone().isoformat(timespec="seconds")


def build_result(entry_url: str, started_at: datetime, finished_at: datetime,
                 findings: List[Dict], topic: str = DEFAULT_TOPIC) -> Dict:
    items = []
    for i, f in enumerate(findings, 1):
        items.append({
            "id": f"f_{i:03d}",
            "url": f["url"],
            "is_violation": bool(f.get("is_violation", True)),
            "location": f["location"],
            "evidence_text": f["evidence_text"],
            "technique": f["technique"],
        })
    return {
        "meta": {
            "topic": topic,
            "entry_url": entry_url,
            "started_at": _iso(started_at),
            "finished_at": _iso(finished_at),
            "elapsed_sec": round((finished_at - started_at).total_seconds(), 2),
            "tool_version": TOOL_VERSION,
        },
        "findings": items,
    }


def validate_result(result: Dict) -> List[str]:
    """문제 목록 반환 (비어 있으면 통과)."""
    errs = []
    meta = result.get("meta")
    if not isinstance(meta, dict):
        return ["meta 없음"]
    for k in ("topic", "entry_url", "started_at", "finished_at", "elapsed_sec", "tool_version"):
        if k not in meta:
            errs.append(f"meta.{k} 없음")
    ids, keys = set(), set()
    for f in result.get("findings", []):
        for k in ("id", "url", "is_violation", "location", "evidence_text", "technique"):
            if k not in f:
                errs.append(f"{f.get('id')}: {k} 없음")
        if f.get("technique") not in TECHNIQUES:
            errs.append(f"{f.get('id')}: technique 값 오류 {f.get('technique')!r}")
        if not f.get("location"):
            errs.append(f"{f.get('id')}: location 비어 있음")
        if f.get("id") in ids:
            errs.append(f"id 중복 {f.get('id')}")
        ids.add(f.get("id"))
        k = (f.get("url"), f.get("location"), f.get("technique"))
        if k in keys:
            errs.append(f"{f.get('id')}: (url, location, technique) 중복")
        keys.add(k)
    return errs


def write_result(result: Dict, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:     # BOM 없는 UTF-8
        json.dump(result, fh, ensure_ascii=False, indent=2)
    return path