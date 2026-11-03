"""OpenAI 클라이언트. .env를 읽는 유일한 모듈."""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import TypeVar

import openai
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from db import repository as repo

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DEFAULT_MODEL = "gpt-6-astra"
T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """사용자에게 그대로 보여줄 수 있는 한국어 오류."""


def settings() -> dict:
    temp = os.getenv("OPENAI_TEMPERATURE", "0.4")
    try:
        temperature = float(temp)
    except ValueError:
        temperature = 0.4
    return {
        "api_key": (os.getenv("OPENAI_API_KEY") or "").strip(),
        "model": (os.getenv("OPENAI_MODEL") or DEFAULT_MODEL).strip(),
        "temperature": temperature,
    }


def is_configured() -> bool:
    return bool(settings()["api_key"])


@lru_cache(maxsize=1)
def _client(api_key: str) -> openai.OpenAI:
    return openai.OpenAI(api_key=api_key, timeout=120, max_retries=2)


def client() -> openai.OpenAI:
    s = settings()
    if not s["api_key"]:
        raise LLMError(".env 파일에 OPENAI_API_KEY가 없습니다. 키를 한 줄로 입력한 뒤 앱을 다시 시작해 주세요.")
    return _client(s["api_key"])


def _friendly(e: Exception, model: str) -> LLMError:
    if isinstance(e, openai.AuthenticationError):
        return LLMError("API 키가 올바르지 않습니다. .env의 OPENAI_API_KEY를 확인해 주세요.")
    if isinstance(e, openai.NotFoundError):
        return LLMError(f"모델 '{model}'을(를) 찾을 수 없습니다. .env의 OPENAI_MODEL 값을 확인해 주세요.")
    if isinstance(e, openai.PermissionDeniedError):
        return LLMError(f"이 API 키로는 모델 '{model}'을(를) 사용할 권한이 없습니다.")
    if isinstance(e, openai.RateLimitError):
        return LLMError("요청 한도 또는 크레딧 한도를 초과했습니다. 잠시 후 다시 시도하거나 OpenAI 결제 상태를 확인해 주세요.")
    if isinstance(e, openai.APITimeoutError):
        return LLMError("AI 응답 시간이 초과되었습니다. 다시 시도해 주세요.")
    if isinstance(e, openai.APIConnectionError):
        return LLMError("OpenAI 서버에 연결할 수 없습니다. 인터넷 연결을 확인해 주세요.")
    if isinstance(e, openai.APIError):
        return LLMError(f"OpenAI API 오류: {getattr(e, 'message', e)}")
    return LLMError(f"알 수 없는 오류: {e}")


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    return json.loads(text)


def chat_json(system: str, user: str, schema: type[T], stage: str) -> T:
    """JSON 응답을 받아 schema로 검증한다. 파싱에 실패하면 1회 재요청한다."""
    s = settings()
    c = client()
    schema_text = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    messages = [
        {"role": "system", "content": f"{system}\n\n응답은 아래 JSON 스키마를 따르는 JSON 객체 하나만 출력하세요.\nJSON 스키마: {schema_text}"},
        {"role": "user", "content": user},
    ]
    opts: dict = {"response_format": {"type": "json_object"}, "temperature": s["temperature"]}

    last_err: Exception | None = None
    for attempt in range(2):
        resp = _create(c, s["model"], messages, opts)
        if resp.usage:
            repo.log_usage(stage, s["model"], resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0)
        content = resp.choices[0].message.content or ""
        try:
            return schema.model_validate(_extract_json(content))
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = e
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user", "content": f"응답이 스키마와 맞지 않습니다({type(e).__name__}). 스키마에 맞는 JSON 객체만 다시 출력하세요."},
            ]
    raise LLMError(f"AI 응답을 해석하지 못했습니다. 다시 시도해 주세요. ({last_err})")


def _create(c: openai.OpenAI, model: str, messages: list, opts: dict):
    """모델이 지원하지 않는 파라미터(temperature, response_format)는 빼고 재시도한다."""
    opts = dict(opts)
    for _ in range(3):
        try:
            return c.chat.completions.create(model=model, messages=messages, **opts)
        except openai.BadRequestError as e:
            msg = str(e).lower()
            dropped = next((k for k in list(opts) if k in msg), None)
            if not dropped:
                raise _friendly(e, model) from e
            opts.pop(dropped)
        except Exception as e:  # noqa: BLE001
            raise _friendly(e, model) from e
    raise LLMError("AI 요청 파라미터를 맞추지 못했습니다.")


def test_connection() -> tuple[bool, str]:
    s = settings()
    try:
        client().models.retrieve(s["model"])
        return True, f"연결 성공: 모델 '{s['model']}' 사용 가능"
    except LLMError as e:
        return False, str(e)
    except Exception as e:  # noqa: BLE001
        return False, str(_friendly(e, s["model"]))
