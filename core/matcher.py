"""② 채용공고 분석과 ③ 경험 매칭 (CL-01, CL-02)."""
from __future__ import annotations

from core import prompts
from core.llm import LLMError, chat_json
from db.models import Experience, MatchItem, MatchResult, PostingAnalysis


def analyze_posting(company: str, position: str, posting: str, company_info: str) -> PostingAnalysis:
    if not (posting.strip() or company_info.strip()):
        raise LLMError("채용공고나 기업 정보를 입력해야 분석할 수 있습니다.")
    return chat_json(
        prompts.POSTING_SYSTEM,
        prompts.posting_user(company, position, posting, company_info),
        PostingAnalysis,
        stage="posting",
    )


def recommend(question: str, position: str, posting_analysis: dict, experiences: list[Experience]) -> list[MatchItem]:
    if not question.strip():
        raise LLMError("문항을 먼저 입력해 주세요.")
    if not experiences:
        raise LLMError("저장된 경험이 없습니다. 경험 저장소에서 경험을 먼저 추가해 주세요.")
    brief = [
        {k: v for k, v in e.for_prompt().items() if k != "원문"} | {"원문요약": e.raw_text[:400]} for e in experiences
    ]
    res = chat_json(
        prompts.MATCH_SYSTEM,
        prompts.match_user(question, position, posting_analysis, brief),
        MatchResult,
        stage="match",
    )
    valid = {e.id for e in experiences}
    seen: set[str] = set()
    items = []
    for m in sorted(res.matches, key=lambda m: m.score, reverse=True):
        if m.experience_id in valid and m.experience_id not in seen:
            seen.add(m.experience_id)
            items.append(m)
    return items
