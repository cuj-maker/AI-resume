"""④ 자기소개서·이력서 생성 (CL-03, CL-04, CL-06, RS-02, RS-03)."""
from __future__ import annotations

import re

from core import prompts
from core.llm import LLMError, chat_json
from db.models import Experience, GeneratedAnswer, Profile, ResumeDraft, ResumeItem


def count_chars(text: str, count_spaces: bool = True) -> int:
    return len(text) if count_spaces else len(re.sub(r"\s", "", text))


def length_status(text: str, char_limit: int, count_spaces: bool) -> str:
    """'ok' | 'short' | 'over' | 'none'"""
    if not char_limit:
        return "none"
    n = count_chars(text, count_spaces)
    if n > char_limit:
        return "over"
    if n < int(char_limit * 0.9):
        return "short"
    return "ok"


def fit_length(answer: str, char_limit: int, count_spaces: bool, experiences: list[Experience]) -> str:
    """목표 글자 수(90~100%)에 맞춰 축약·확장한다. 이미 범위 안이면 그대로 돌려준다.
    조정 결과가 범위에 더 가까울 때만 채택하며, 새로운 사실은 추가하지 않는다."""
    if not answer.strip() or length_status(answer, char_limit, count_spaces) not in ("short", "over"):
        return answer
    facts = [e.for_prompt() for e in experiences]
    adjusted = chat_json(
        prompts.ADJUST_SYSTEM,
        prompts.adjust_user(answer, count_chars(answer, count_spaces), char_limit, count_spaces, facts),
        GeneratedAnswer,
        stage="adjust",
    ).answer.strip()
    if not adjusted:
        return answer
    n_before, n_after = count_chars(answer, count_spaces), count_chars(adjusted, count_spaces)
    target = char_limit * 0.95
    if (n_before > char_limit >= n_after) or abs(n_after - target) < abs(n_before - target):
        return adjusted
    return answer


def generate_answer(
    *,
    company: str,
    position: str,
    question: str,
    char_limit: int,
    count_spaces: bool,
    tone: str,
    posting_analysis: dict,
    company_info: str,
    experiences: list[Experience],
    previous: str = "",
    instruction: str = "",
) -> GeneratedAnswer:
    if not question.strip():
        raise LLMError("문항을 입력해 주세요.")
    if not experiences:
        raise LLMError("답변에 사용할 경험을 하나 이상 선택해 주세요.")
    facts = [e.for_prompt() for e in experiences]
    res = chat_json(
        prompts.WRITE_SYSTEM,
        prompts.write_user(
            company=company,
            position=position,
            question=question,
            char_limit=char_limit,
            count_spaces=count_spaces,
            tone=tone,
            posting_analysis=posting_analysis,
            company_info=company_info,
            experiences=facts,
            previous=previous,
            instruction=instruction,
        ),
        GeneratedAnswer,
        stage="write",
    )
    # 분량이 범위를 벗어나면 1회 자동 조정 (CL-04)
    res.answer = fit_length(res.answer.strip(), char_limit, count_spaces, experiences)

    valid = {e.id for e in experiences}
    res.used_experience_ids = [i for i in res.used_experience_ids if i in valid] or [e.id for e in experiences]
    return res


def generate_resume(profile: Profile, experiences: list[Experience], position: str, posting_analysis: dict) -> ResumeDraft:
    if not experiences:
        raise LLMError("이력서에 넣을 경험을 하나 이상 선택해 주세요.")
    prof = profile.model_dump(exclude={"id", "updated_at", "email", "phone", "links"})
    res = chat_json(
        prompts.RESUME_SYSTEM,
        prompts.resume_user(position, posting_analysis, prof, [e.for_prompt() for e in experiences]),
        ResumeDraft,
        stage="resume",
    )
    valid = {e.id for e in experiences}
    seen: set[str] = set()
    items = []
    for it in sorted(res.items, key=lambda i: i.relevance, reverse=True):
        if it.experience_id in valid and it.experience_id not in seen:
            seen.add(it.experience_id)
            items.append(it)
    # AI가 빠뜨린 경험도 목록 끝에 유지
    items += [ResumeItem(experience_id=e.id, relevance=0, bullets=[]) for e in experiences if e.id not in seen]
    res.items = items
    return res
