"""⑤ 사실 검증 (CL-05)."""
from __future__ import annotations

import html

from core import prompts
from core.llm import chat_json
from db.models import Experience, VerificationItem, VerificationResult


def verify(answer: str, experiences: list[Experience], company_info: str) -> list[VerificationItem]:
    if not answer.strip():
        return []
    res = chat_json(
        prompts.VERIFY_SYSTEM,
        prompts.verify_user(answer, [e.for_prompt() for e in experiences], company_info),
        VerificationResult,
        stage="verify",
    )
    return res.items


def unsupported_ratio(items: list[dict]) -> float:
    if not items:
        return 0.0
    return sum(1 for i in items if not i.get("supported", True)) / len(items)


def highlight(answer: str, items: list[dict]) -> str:
    """근거 없는 문장을 <mark>로 감싼 HTML을 만든다. 답변 원문은 이스케이프한다."""
    text = html.escape(answer)
    for it in items:
        if it.get("supported", True):
            continue
        sent = html.escape((it.get("sentence") or "").strip())
        if sent and sent in text:
            tip = html.escape(it.get("source") or "근거 없음", quote=True)
            text = text.replace(sent, f'<mark class="unsupported" title="{tip}">{sent}</mark>', 1)
    return text.replace("\n", "<br>")
