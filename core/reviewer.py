"""AI 자기소개서 첨삭: 자연스러움·중복·흐름·STAR·직무 연관성·구체성·근거 부족 점검."""
from __future__ import annotations

from core import prompts
from core.llm import LLMError, chat_json
from core.writer import fit_length
from db.models import Experience, ReviewResult


def review(*, question: str, answer: str, company: str, position: str, posting_analysis: dict,
           experiences: list[Experience], char_limit: int, count_spaces: bool) -> ReviewResult:
    if not answer.strip():
        raise LLMError("첨삭할 답변이 없습니다.")
    if not experiences:
        raise LLMError("첨삭의 사실 근거가 될 경험을 하나 이상 선택해 주세요.")
    res = chat_json(
        prompts.REVIEW_SYSTEM,
        prompts.review_user(question=question, answer=answer, company=company, position=position,
                            posting_analysis=posting_analysis, experiences=[e.for_prompt() for e in experiences],
                            char_limit=char_limit, count_spaces=count_spaces),
        ReviewResult,
        stage="review",
    )
    # 원문에 없는 '중복 표현'·'추상 표현'은 버린다 (모델이 표현을 바꿔 인용하는 경우)
    res.duplicates = [d for d in res.duplicates if d.strip() and d.strip() in answer]
    res.abstract_expressions = [r for r in res.abstract_expressions if r.original.strip() and r.original.strip() in answer]
    res.revised = fit_length(res.revised.strip(), char_limit, count_spaces, experiences) if res.revised.strip() else ""
    return res
