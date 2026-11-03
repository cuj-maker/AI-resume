"""저장 데이터 모델과 LLM 응답 스키마."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

EXPERIENCE_TYPES = ["회사 경력", "인턴", "프로젝트", "대외활동", "아르바이트", "동아리", "수상 경력", "기타"]
TONES = ["담백함", "논리적", "열정적", "진솔함"]
APP_STATUSES = ["작성 중", "제출 완료", "서류 합격", "서류 불합격", "면접 진행", "최종 합격", "최종 불합격", "지원 취소"]
CHAR_PRESETS = [300, 500, 700, 1000, 1500]
INTERVIEW_CATEGORIES = ["자소서 기반", "꼬리 질문", "직무 질문"]
# 이력서 섹션: (제목, 해당 경험 유형)
RESUME_SECTIONS = [
    ("경력", ["회사 경력", "인턴"]),
    ("프로젝트", ["프로젝트"]),
    ("대외활동 · 기타 경험", ["대외활동", "동아리", "아르바이트", "기타"]),
    ("수상 경력", ["수상 경력"]),
]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex


# ─────────────────────────── 저장 데이터 ───────────────────────────
class Experience(BaseModel):
    id: str = Field(default_factory=new_id)
    type: str = "프로젝트"
    title: str = ""
    organization: str = ""
    role: str = ""
    start_date: str = ""  # YYYY-MM
    end_date: str = ""  # YYYY-MM
    ongoing: bool = False
    raw_text: str = ""
    situation: str = ""
    task: str = ""
    action: str = ""
    result: str = ""
    keywords: list[str] = Field(default_factory=list)
    competencies: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    @property
    def period(self) -> str:
        if not self.start_date:
            return ""
        end = "진행 중" if self.ongoing else (self.end_date or "")
        return f"{self.start_date} ~ {end}".strip()

    def for_prompt(self) -> dict:
        """프롬프트에 넣을 사실 자료 (원문 + STAR)."""
        return {
            "experience_id": self.id,
            "유형": self.type,
            "제목": self.title,
            "소속": self.organization,
            "역할": self.role,
            "기간": self.period,
            "원문": self.raw_text,
            "STAR": {"S": self.situation, "T": self.task, "A": self.action, "R": self.result},
            "핵심역량": self.competencies,
            "키워드": self.keywords,
        }


class Profile(BaseModel):
    id: str = "me"
    name: str = ""
    email: str = ""
    phone: str = ""
    links: str = ""
    education: str = ""
    certifications: str = ""
    languages: str = ""
    skills: str = ""
    training: str = ""  # 교육 및 수료
    updated_at: str = Field(default_factory=now_iso)


class Application(BaseModel):
    id: str = Field(default_factory=new_id)
    company: str = ""
    position: str = ""
    job_posting: str = ""
    company_info: str = ""
    tone: str = TONES[0]
    posting_analysis: dict = Field(default_factory=dict)
    status: str = APP_STATUSES[0]
    applied_date: str = ""  # YYYY-MM-DD
    memo: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class AppVersion(BaseModel):
    """지원서 작성 버전 스냅샷. is_final=True가 최종 제출본."""
    id: str = Field(default_factory=new_id)
    application_id: str
    label: str = ""
    snapshot: dict = Field(default_factory=dict)  # {"application": {...}, "answers": [...]}
    is_final: bool = False
    created_at: str = Field(default_factory=now_iso)


class InterviewItem(BaseModel):
    id: str = Field(default_factory=new_id)
    application_id: str = ""  # 빈 값이면 지원서 없이 직무만으로 만든 질문
    position: str = ""
    category: str = INTERVIEW_CATEGORIES[0]
    question: str = ""
    intent: str = ""
    experience_id: str = ""
    model_answer: str = ""
    tips: list[str] = Field(default_factory=list)
    user_answer: str = ""
    evaluation: dict = Field(default_factory=dict)
    order_no: int = 0
    created_at: str = Field(default_factory=now_iso)


class Answer(BaseModel):
    id: str = Field(default_factory=new_id)
    application_id: str
    order_no: int = 0
    question: str = ""
    char_limit: int = 0  # 0 = 제한 없음
    count_spaces: bool = True
    content: str = ""
    used_experience_ids: list[str] = Field(default_factory=list)
    verification: list[dict] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)


class UsageLog(BaseModel):
    id: str = Field(default_factory=new_id)
    stage: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    created_at: str = Field(default_factory=now_iso)


# ─────────────────────────── LLM 응답 스키마 ───────────────────────────
class StarAnalysis(BaseModel):
    situation: str = ""
    task: str = ""
    action: str = ""
    result: str = ""
    keywords: list[str] = Field(default_factory=list)
    competencies: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)


class PostingAnalysis(BaseModel):
    required_skills: list[str] = Field(default_factory=list)
    preferred: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    culture: list[str] = Field(default_factory=list)


class MatchItem(BaseModel):
    experience_id: str
    score: int = Field(ge=0, le=100)
    reason: str = ""


class MatchResult(BaseModel):
    matches: list[MatchItem] = Field(default_factory=list)


class GeneratedAnswer(BaseModel):
    answer: str
    used_experience_ids: list[str] = Field(default_factory=list)


class VerificationItem(BaseModel):
    sentence: str
    supported: bool
    source: str = ""


class VerificationResult(BaseModel):
    items: list[VerificationItem] = Field(default_factory=list)


class ResumeItem(BaseModel):
    experience_id: str
    relevance: int = Field(default=0, ge=0, le=100)
    bullets: list[str] = Field(default_factory=list)


class ResumeDraft(BaseModel):
    summary: str = ""
    core_competencies: list[str] = Field(default_factory=list)
    items: list[ResumeItem] = Field(default_factory=list)


class ReviewScores(BaseModel):
    naturalness: int = Field(default=0, ge=0, le=100)
    logic: int = Field(default=0, ge=0, le=100)
    job_relevance: int = Field(default=0, ge=0, le=100)
    specificity: int = Field(default=0, ge=0, le=100)


class StarCheck(BaseModel):
    situation: bool = False
    task: bool = False
    action: bool = False
    result: bool = False
    comment: str = ""


class Rewrite(BaseModel):
    original: str
    suggestion: str
    reason: str = ""


class EvidenceGap(BaseModel):
    sentence: str
    need: str


class ReviewResult(BaseModel):
    scores: ReviewScores = Field(default_factory=ReviewScores)
    star_check: StarCheck = Field(default_factory=StarCheck)
    duplicates: list[str] = Field(default_factory=list)
    abstract_expressions: list[Rewrite] = Field(default_factory=list)
    missing_evidence: list[EvidenceGap] = Field(default_factory=list)
    flow_feedback: str = ""
    job_relevance_comment: str = ""
    revised: str = ""


class InterviewQ(BaseModel):
    category: str
    question: str
    intent: str = ""
    experience_id: str = ""


class InterviewQuestions(BaseModel):
    questions: list[InterviewQ] = Field(default_factory=list)


class InterviewAnswer(BaseModel):
    answer: str
    tips: list[str] = Field(default_factory=list)


class AnswerEvaluation(BaseModel):
    logic: int = Field(default=0, ge=0, le=100)
    specificity: int = Field(default=0, ge=0, le=100)
    star: StarCheck = Field(default_factory=StarCheck)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    summary: str = ""
