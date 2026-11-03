"""TXT / Markdown / DOCX 내보내기 (CL-09, RS-04)."""
from __future__ import annotations

import io

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt

from core.writer import count_chars
from db.models import (
    INTERVIEW_CATEGORIES,
    RESUME_SECTIONS,
    Answer,
    Application,
    Experience,
    InterviewItem,
    Profile,
    ResumeDraft,
)

FONT = "Malgun Gothic"


def _len_label(a: Answer) -> str:
    n = count_chars(a.content, a.count_spaces)
    basis = "공백 포함" if a.count_spaces else "공백 제외"
    return f"{n}자 / {a.char_limit}자 ({basis})" if a.char_limit else f"{n}자"


# ─────────────────────────── 자기소개서 ───────────────────────────
def cover_letter_md(app: Application, answers: list[Answer]) -> str:
    out = [f"# {app.company} · {app.position} 자기소개서", ""]
    for i, a in enumerate(answers, 1):
        out += [f"## {i}. {a.question}", f"*{_len_label(a)}*", "", a.content, ""]
    return "\n".join(out)


def cover_letter_txt(app: Application, answers: list[Answer]) -> str:
    out = [f"{app.company} · {app.position} 자기소개서", "=" * 30, ""]
    for i, a in enumerate(answers, 1):
        out += [f"{i}. {a.question}  [{_len_label(a)}]", "", a.content, "", "-" * 30, ""]
    return "\n".join(out)


def _new_doc() -> Document:
    doc = Document()
    for style_name in ("Normal", "Heading 1", "Heading 2", "Heading 3", "Title"):
        st = doc.styles[style_name]
        st.font.name = FONT
        rpr = st.element.get_or_add_rPr()
        rpr.get_or_add_rFonts().set(qn("w:eastAsia"), FONT)
    doc.styles["Normal"].font.size = Pt(10.5)
    return doc


def _bytes(doc: Document) -> bytes:
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def cover_letter_docx(app: Application, answers: list[Answer]) -> bytes:
    doc = _new_doc()
    doc.add_heading(f"{app.company} · {app.position} 자기소개서", level=1)
    for i, a in enumerate(answers, 1):
        doc.add_heading(f"{i}. {a.question}", level=2)
        doc.add_paragraph(_len_label(a)).runs[0].italic = True
        for para in a.content.split("\n"):
            if para.strip():
                doc.add_paragraph(para.strip())
    return _bytes(doc)


# ─────────────────────────── 이력서 ───────────────────────────
def _contact(p: Profile) -> str:
    return " | ".join(x for x in (p.email, p.phone, p.links) if x)


def _exp_header(e: Experience) -> str:
    parts = [e.title, e.organization, e.role, e.period]
    return " | ".join(p for p in parts if p)


def resume_blocks(p: Profile, draft: ResumeDraft, exps: dict[str, Experience]) -> list[tuple[str, list]]:
    """이력서 섹션 목록: [(제목, [(소제목 | None, [줄...]), ...]), ...]. 비어 있는 섹션은 뺀다.
    경험은 유형별 섹션(경력/프로젝트/대외활동/수상)으로 나누고, 섹션 안에서는 관련도 순서를 유지한다."""
    def text_lines(v: str) -> list:
        return [(None, [line.strip() for line in v.split("\n") if line.strip()])] if v.strip() else []

    blocks: list[tuple[str, list]] = []
    if draft.summary.strip():
        blocks.append(("요약", [(None, [draft.summary.strip()])]))
    if draft.core_competencies:
        blocks.append(("핵심 역량", [(None, [" · ".join(draft.core_competencies)])]))
    blocks.append(("학력", text_lines(p.education)))
    for title, types in RESUME_SECTIONS:
        entries = []
        for it in draft.items:
            e = exps.get(it.experience_id)
            if e and e.type in types:
                entries.append((_exp_header(e), [f"- {b}" for b in it.bullets]))
        blocks.append((title, entries))
    blocks += [
        ("보유 기술", text_lines(p.skills)),
        ("자격증", text_lines(p.certifications)),
        ("교육 및 수료", text_lines(p.training)),
        ("어학", text_lines(p.languages)),
    ]
    return [(t, b) for t, b in blocks if b]


def resume_md(p: Profile, draft: ResumeDraft, exps: dict[str, Experience], position: str = "") -> str:
    out = [f"# {p.name or '이름'}" + (f" — {position}" if position else "")]
    if _contact(p):
        out.append(_contact(p))
    for title, entries in resume_blocks(p, draft, exps):
        out += ["", f"## {title}"]
        for sub, lines in entries:
            if sub:
                out += ["", f"### {sub}"]
            out += lines
    return "\n".join(out) + "\n"


def resume_docx(p: Profile, draft: ResumeDraft, exps: dict[str, Experience], position: str = "") -> bytes:
    doc = _new_doc()
    doc.add_heading(f"{p.name or '이름'}" + (f" — {position}" if position else ""), level=1)
    if _contact(p):
        doc.add_paragraph(_contact(p))
    for title, entries in resume_blocks(p, draft, exps):
        doc.add_heading(title, level=2)
        for sub, lines in entries:
            if sub:
                doc.add_heading(sub, level=3)
            for line in lines:
                if line.startswith("- "):
                    doc.add_paragraph(line[2:], style="List Bullet")
                else:
                    doc.add_paragraph(line)
    return _bytes(doc)


# ─────────────────────────── 면접 준비 ───────────────────────────
def interview_md(title: str, items: list[InterviewItem]) -> str:
    out = [f"# {title} 면접 준비", ""]
    for cat in INTERVIEW_CATEGORIES:
        group = [i for i in items if i.category == cat]
        if not group:
            continue
        out += [f"## {cat}", ""]
        for n, it in enumerate(group, 1):
            out += [f"### Q{n}. {it.question}"]
            if it.intent:
                out += [f"*의도: {it.intent}*"]
            if it.model_answer:
                out += ["", "**STAR 모범 답변**", "", it.model_answer]
            if it.tips:
                out += [""] + [f"- {t}" for t in it.tips]
            if it.user_answer:
                out += ["", "**내 답변**", "", it.user_answer]
            ev = it.evaluation
            if ev:
                out += ["", f"**평가**: 논리성 {ev.get('logic', 0)} · 구체성 {ev.get('specificity', 0)} — {ev.get('summary', '')}"]
            out.append("")
    return "\n".join(out)
