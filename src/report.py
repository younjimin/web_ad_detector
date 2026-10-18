"""탐지 결과(result dict)를 하나의 HTML 파일로 만든다. 외부 파일/네트워크 없이 열린다."""
import html
from datetime import datetime
from pathlib import Path
from typing import Dict, List

TECH_INFO = {
    "HOMOGLYPH": ("닮은꼴 글자 위장", "키릴·전각 문자나 숫자·기호로 글자를 바꿔 필터를 피하는 기법"),
    "JAMO": ("자모 분해", "음절을 자모 단위로 쪼개 키워드 검사를 피하는 기법"),
    "TRANSPARENT": ("투명 텍스트", "배경색과 같은 글자색, opacity:0, color:transparent 등으로 글을 보이지 않게 하는 기법"),
    "OFFSCREEN": ("화면 밖 은닉", "font-size 0~1px, 화면 밖 좌표(left:-9999px), display:none 등으로 숨기는 기법"),
}
COLORS = {"HOMOGLYPH": "#b45309", "JAMO": "#7c3aed", "TRANSPARENT": "#0369a1", "OFFSCREEN": "#be123c"}

_CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2430;--mute:#5b6675;--line:#e3e7ee;--accent:#1d4ed8}
@media (prefers-color-scheme:dark){:root{--bg:#0f141b;--card:#171e28;--ink:#e6ebf2;--mute:#9aa6b6;--line:#2a3442;--accent:#7aa2ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 "Malgun Gothic","Noto Sans KR",system-ui,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:24px 16px 60px}
h1{font-size:22px;margin:0 0 4px}.sub{color:var(--mute);font-size:13px;word-break:break-all}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:20px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card .n{font-size:28px;font-weight:700}.card .l{font-size:13px;color:var(--mute)}
.bar{height:8px;border-radius:4px;background:var(--line);margin-top:8px;overflow:hidden}.bar i{display:block;height:100%}
.tools{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:8px 0 12px}
.tools button,.tools input{font:inherit;padding:6px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}
.tools button.on{background:var(--accent);border-color:var(--accent);color:#fff}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:9px 10px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line);font-size:13.5px}
th{background:var(--bg);color:var(--mute);font-weight:600}tr:last-child td{border-bottom:0}
code{font:12.5px/1.5 ui-monospace,Consolas,monospace;word-break:break-all}
.tag{display:inline-block;padding:2px 8px;border-radius:999px;color:#fff;font-size:12px;white-space:nowrap}
.why{color:var(--mute);font-size:12.5px;margin-top:4px}
.empty{padding:28px;text-align:center;color:var(--mute);background:var(--card);border:1px solid var(--line);border-radius:10px}
details{margin-top:22px;color:var(--mute)}summary{cursor:pointer}
@media (max-width:700px){th:nth-child(4),td:nth-child(4){display:none}}
"""

_JS = """
const rows=[...document.querySelectorAll('#tb tr')];let tech='ALL';
function apply(){const q=document.getElementById('q').value.toLowerCase();let n=0;
rows.forEach(r=>{const ok=(tech==='ALL'||r.dataset.t===tech)&&r.textContent.toLowerCase().includes(q);r.style.display=ok?'':'none';if(ok)n++;});
document.getElementById('cnt').textContent=n+'건 표시';}
document.querySelectorAll('[data-f]').forEach(b=>b.onclick=()=>{tech=b.dataset.f;document.querySelectorAll('[data-f]').forEach(x=>x.classList.toggle('on',x===b));apply();});
document.getElementById('q').oninput=apply;apply();
"""


def build_report_html(result: Dict, details: Dict = None) -> str:
    """details: {(url, location, technique): '판정 이유 문장'} (없어도 된다)"""
    details = details or {}
    meta = result.get("meta", {})
    findings: List[Dict] = result.get("findings", [])
    e = html.escape
    counts = {t: sum(1 for f in findings if f["technique"] == t) for t in TECH_INFO}
    total = len(findings)

    cards = [f'<div class="card"><div class="n">{total}</div><div class="l">총 탐지 건수</div></div>']
    for t, (ko, _) in TECH_INFO.items():
        pct = (counts[t] * 100 // total) if total else 0
        cards.append(
            f'<div class="card"><div class="n" style="color:{COLORS[t]}">{counts[t]}</div>'
            f'<div class="l">{e(ko)} · {t}</div>'
            f'<div class="bar"><i style="width:{pct}%;background:{COLORS[t]}"></i></div></div>')

    if findings:
        trs = []
        for f in findings:
            t = f["technique"]
            why = details.get((f["url"], f["location"], t), "")
            why_html = f'<div class="why">{e(why)}</div>' if why else ""
            trs.append(
                f'<tr data-t="{t}"><td>{e(f["id"])}</td>'
                f'<td><span class="tag" style="background:{COLORS.get(t, "#555")}">{e(TECH_INFO.get(t, (t,))[0])}</span></td>'
                f'<td><a href="{e(f["url"])}" target="_blank" rel="noopener">{e(f["url"])}</a></td>'
                f'<td><code>{e(f["location"])}</code></td>'
                f'<td>{e(f["evidence_text"])}{why_html}</td></tr>')
        table = ('<table><thead><tr><th>ID</th><th>유형</th><th>페이지</th><th>위치(CSS 선택자)</th><th>근거 원문</th></tr></thead>'
                 f'<tbody id="tb">{"".join(trs)}</tbody></table>')
    else:
        table = '<div class="empty">탐지된 불법광고가 없습니다.</div><table style="display:none"><tbody id="tb"></tbody></table>'

    filters = '<button class="on" data-f="ALL">전체</button>' + "".join(
        f'<button data-f="{t}">{e(ko)}</button>' for t, (ko, _) in TECH_INFO.items())
    legend = "".join(f"<p><b>{e(ko)} ({t})</b> — {e(desc)}</p>" for t, (ko, desc) in TECH_INFO.items())

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>불법광고 탐지 결과 리포트</title><style>{_CSS}</style></head><body><div class="wrap">
<h1>불법광고 탐지 결과 리포트</h1>
<div class="sub">진입 URL: {e(str(meta.get("entry_url", "")))}<br>
시작 {e(str(meta.get("started_at", "")))} · 종료 {e(str(meta.get("finished_at", "")))} · 소요 {e(str(meta.get("elapsed_sec", "")))}초 · 도구 버전 {e(str(meta.get("tool_version", "")))}</div>
<div class="cards">{"".join(cards)}</div>
<div class="tools">{filters}<input id="q" type="search" placeholder="URL·위치·근거 검색"><span id="cnt" class="sub"></span></div>
{table}
<details><summary>탐지 유형 설명</summary>{legend}</details>
<div class="sub" style="margin-top:18px">생성 시각 {datetime.now().astimezone().isoformat(timespec="seconds")}</div>
</div><script>{_JS}</script></body></html>"""


def write_report(result: Dict, path, details: Dict = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_report_html(result, details), encoding="utf-8", newline="\n")
    return path