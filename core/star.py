"""① STAR 분석과 키워드·역량 추출 (EXP-02, EXP-03, EXP-07)."""
from __future__ import annotations

import re

from core import prompts
from core.llm import LLMError, chat_json
from db.models import StarAnalysis


def analyze(*, type_: str, title: str, organization: str, role: str, period: str, raw_text: str) -> StarAnalysis:
    if not raw_text.strip():
        raise LLMError("경험 원문을 먼저 입력해 주세요.")
    meta = {"유형": type_, "제목": title, "소속": organization, "역할": role, "기간": period}
    res = chat_json(prompts.STAR_SYSTEM, prompts.star_user(meta, raw_text), StarAnalysis, stage="star")
    res.keywords = _dedupe(res.keywords)[:10]
    res.competencies = _dedupe(res.competencies)[:5]
    # 태그로 보여 주므로 '[보완 필요: ...]' 감싸기를 벗긴다
    res.missing_info = _dedupe([re.sub(r"^\[?\s*보완 필요\s*:\s*|\]$", "", m).strip() for m in res.missing_info])
    return res


def merge_follow_up(raw_text: str, qa: list[tuple[str, str]]) -> str:
    """보완 질문 답변을 원문에 덧붙인다. 답변도 사용자가 쓴 사실이므로 원문에 포함해 근거로 쓴다."""
    lines = [f"- {q}\n  → {a.strip()}" for q, a in qa if a.strip()]
    if not lines:
        return raw_text
    return raw_text.rstrip() + "\n\n[보완 답변]\n" + "\n".join(lines)


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for s in items:
        s = s.strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out
