"""면접 준비: 예상 질문·꼬리 질문·직무 질문 생성, STAR 답변 작성, 답변 평가."""
from __future__ import annotations

from core import prompts
from core.llm import LLMError, chat_json
from db.models import (
    INTERVIEW_CATEGORIES,
    AnswerEvaluation,
    Answer,
    Experience,
    InterviewAnswer,
    InterviewQ,
    InterviewQuestions,
)


def generate_questions(*, company: str, position: str, posting_analysis: dict, answers: list[Answer],
                       experiences: list[Experience], counts: dict[str, int]) -> list[InterviewQ]:
    counts = {k: int(v) for k, v in counts.items() if k in INTERVIEW_CATEGORIES and int(v) > 0}
    if not counts:
        raise LLMError("만들 질문 유형과 개수를 선택해 주세요.")
    if "자소서 기반" in counts and not any(a.content.strip() for a in answers):
        raise LLMError("'자소서 기반' 질문을 만들려면 답변이 작성된 지원서를 선택해 주세요.")
    if "꼬리 질문" in counts and not experiences:
        raise LLMError("'꼬리 질문'을 만들 경험을 선택해 주세요.")
    if "직무 질문" in counts and not position.strip():
        raise LLMError("'직무 질문'을 만들려면 지원 직무를 입력해 주세요.")
    res = chat_json(
        prompts.INTERVIEW_Q_SYSTEM,
        prompts.interview_q_user(
            company=company, position=position, posting_analysis=posting_analysis,
            answers=[{"문항": a.question, "답변": a.content} for a in answers if a.content.strip()],
            experiences=[e.for_prompt() for e in experiences], counts=counts,
        ),
        InterviewQuestions,
        stage="interview_q",
    )
    valid = {e.id for e in experiences}
    out = []
    for q in res.questions:
        if q.category not in counts or not q.question.strip():
            continue
        if q.experience_id not in valid:
            q.experience_id = ""
        out.append(q)
    # 유형별 요청 개수를 넘으면 자른다
    per: dict[str, int] = {}
    trimmed = []
    for q in out:
        per[q.category] = per.get(q.category, 0) + 1
        if per[q.category] <= counts[q.category]:
            trimmed.append(q)
    return trimmed


def star_answer(*, question: str, intent: str, company: str, position: str,
                experiences: list[Experience]) -> InterviewAnswer:
    if not experiences:
        raise LLMError("답변에 사용할 경험이 없습니다. 경험 저장소에 경험을 추가해 주세요.")
    res = chat_json(
        prompts.INTERVIEW_A_SYSTEM,
        prompts.interview_a_user(question=question, intent=intent, company=company, position=position,
                                 experiences=[e.for_prompt() for e in experiences]),
        InterviewAnswer,
        stage="interview_a",
    )
    res.answer = res.answer.strip()
    return res


def evaluate(question: str, user_answer: str, experiences: list[Experience]) -> AnswerEvaluation:
    if not user_answer.strip():
        raise LLMError("평가받을 내 답변을 먼저 입력해 주세요.")
    return chat_json(
        prompts.EVAL_SYSTEM,
        prompts.eval_user(question, user_answer, [e.for_prompt() for e in experiences]),
        AnswerEvaluation,
        stage="interview_eval",
    )
