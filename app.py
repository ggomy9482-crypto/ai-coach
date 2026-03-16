import csv
import os
from datetime import datetime
from pathlib import Path

from flask import Flask, redirect, render_template, request, session, url_for

# -----------------------------
# Basic Flask app configuration
# -----------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "ai-invention-coach-secret")

# -----------------------------
# Project constants (easy to edit)
# -----------------------------
WEEKLY_TOPIC = "학교생활을 더 편리하게 만드는 발명"
DATA_DIR = Path("data")
CSV_PATH = DATA_DIR / "results.csv"
CSV_HEADERS = [
    "timestamp",
    "grade",
    "language",
    "topic",
    "problem",
    "when_happens",
    "who_affected",
    "why_happens",
    "invention_directions",
    "final_idea",
    "note_summary",
]

# Dictionary structure for future multilingual UI expansion
UI_LABELS = {
    "ko": {
        "app_title": "AI 발명 코치",
        "weekly_topic": "이번 주 발명 주제",
        "start": "시작하기",
    },
    "en": {
        "app_title": "AI Invention Coach",
        "weekly_topic": "Weekly Invention Topic",
        "start": "Start",
    },
    "zh": {
        "app_title": "AI 发明教练",
        "weekly_topic": "每周发明主题",
        "start": "开始",
    },
    "vi": {
        "app_title": "Huấn luyện viên Phát minh AI",
        "weekly_topic": "Chủ đề phát minh tuần này",
        "start": "Bắt đầu",
    },
}


def ensure_csv_file() -> None:
    """Create data folder and CSV file safely when app starts."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CSV_PATH.exists():
        with CSV_PATH.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(CSV_HEADERS)


def get_ui_labels(language: str) -> dict:
    """Return UI labels for selected language. Korean is default."""
    return UI_LABELS.get(language, UI_LABELS["ko"])


def call_openai_text(prompt: str) -> str:
    """Try OpenAI call. If unavailable, raise exception so fallback is used."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    from openai import OpenAI  # imported here to keep dependency optional

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model="gpt-4o-mini",
        input=prompt,
        temperature=0.6,
    )
    return response.output_text.strip()


# ---------------------------------------------------
# Required modular AI generation functions (v1 design)
# ---------------------------------------------------
def generate_coaching_questions(problem: str, grade: str, language: str):
    """Generate 3 coaching questions for student reflection."""
    prompt = (
        f"초등학생(학년: {grade}, 언어: {language})을 위한 발명 코칭 질문 3개를 작성하세요. "
        f"문제: {problem}\n"
        "반드시 다음 주제를 각각 한 개씩 포함하세요: 언제 발생하는가, 누가 가장 영향을 받는가, 왜 발생한다고 생각하는가. "
        "질문만 한 줄에 하나씩 출력하세요."
    )

    try:
        text = call_openai_text(prompt)
        lines = [line.strip(" -0123456789.") for line in text.splitlines() if line.strip()]
        if len(lines) >= 3:
            return lines[:3]
    except Exception:
        pass

    # Fallback questions (required)
    return [
        "이 불편함은 언제 가장 많이 생기나요?",
        "누가 이 문제 때문에 가장 불편한가요?",
        "왜 이런 일이 생긴다고 생각하나요?",
    ]


def generate_invention_directions(problem: str, answers: dict, grade: str, language: str):
    """Generate 2-3 invention directions without giving final answer."""
    prompt = (
        f"초등학생 발명 수업 코치 역할을 하세요. 언어: {language}, 학년: {grade}\n"
        f"문제: {problem}\n"
        f"답변: {answers}\n"
        "최종 정답은 주지 말고, 발명 방향 아이디어 2~3개를 짧게 제시하세요. "
        "학생을 짧게 격려하고, 마지막 줄에는 열린 생각 질문 1개를 작성하세요. "
        "출력 형식:\n"
        "방향1: ...\n방향2: ...\n(필요하면 방향3)\n격려: ...\n생각질문: ..."
    )

    try:
        text = call_openai_text(prompt)
        directions = []
        encouragement = ""
        open_question = ""
        for line in text.splitlines():
            clean = line.strip()
            if not clean:
                continue
            if clean.startswith("방향"):
                directions.append(clean.split(":", 1)[-1].strip())
            elif clean.startswith("격려"):
                encouragement = clean.split(":", 1)[-1].strip()
            elif clean.startswith("생각질문"):
                open_question = clean.split(":", 1)[-1].strip()
        if directions:
            return {
                "directions": directions[:3],
                "encouragement": encouragement or "좋은 관찰이에요! 한 단계씩 생각해 봅시다.",
                "open_question": open_question or "이 문제를 더 쉽게 해결하려면 무엇을 먼저 바꿔보면 좋을까요?",
            }
    except Exception:
        pass

    # Fallback directions (required)
    return {
        "directions": [
            "기억을 도와주는 방법",
            "헷갈리지 않게 구분하는 방법",
            "여러 사람이 함께 사용하기 쉽게 만드는 방법",
        ],
        "encouragement": "관찰을 아주 잘했어요! 이제 해결 방향을 골라봅시다.",
        "open_question": "이 방향을 실제 학교생활에서 사용하려면 어떤 모습이어야 할까요?",
    }


def generate_invention_note(topic: str, problem: str, answers: dict, direction: str, final_idea: str):
    """Generate final invention note summary."""
    prompt = (
        "다음 정보를 바탕으로 초등학생용 발명 노트를 간단하고 구조적으로 정리하세요.\n"
        f"주제: {topic}\n"
        f"문제: {problem}\n"
        f"언제: {answers.get('when', '')}\n"
        f"누가: {answers.get('who', '')}\n"
        f"왜: {answers.get('why', '')}\n"
        f"발명 방향: {direction}\n"
        f"최종 아이디어: {final_idea}\n"
        "3~6문장으로 한국어 요약만 출력하세요."
    )

    try:
        text = call_openai_text(prompt)
        if text:
            return text
    except Exception:
        pass

    # Fallback note format (required)
    return (
        f"[발명 노트]\n"
        f"- 이번 주 주제: {topic}\n"
        f"- 발견한 문제: {problem}\n"
        f"- 언제 생기나요: {answers.get('when', '')}\n"
        f"- 누가 불편한가요: {answers.get('who', '')}\n"
        f"- 왜 생기나요: {answers.get('why', '')}\n"
        f"- 발명 방향: {direction}\n"
        f"- 나의 발명 아이디어: {final_idea}"
    )


def save_result_to_csv(record: dict) -> None:
    """Append one student result to CSV."""
    ensure_csv_file()
    with CSV_PATH.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_HEADERS)
        writer.writerow(record)


def load_results_from_csv():
    """Read all saved student results for teacher page."""
    ensure_csv_file()
    rows = []
    with CSV_PATH.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            rows.append(row)
    rows.reverse()  # newest first
    return rows


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        language = request.form.get("language", "ko")
        grade = request.form.get("grade", "3")

        session.clear()
        session["language"] = language
        session["grade"] = grade
        session["topic"] = WEEKLY_TOPIC

        return redirect(url_for("question"))

    language = session.get("language", "ko")
    return render_template(
        "index.html",
        labels=get_ui_labels(language),
        weekly_topic=WEEKLY_TOPIC,
    )


@app.route("/question", methods=["GET", "POST"])
def question():
    if "topic" not in session:
        return redirect(url_for("index"))

    coaching_questions = session.get("coaching_questions")

    if request.method == "POST":
        form_type = request.form.get("form_type")

        if form_type == "problem":
            problem = request.form.get("problem", "").strip()
            if problem:
                session["problem"] = problem
                coaching_questions = generate_coaching_questions(
                    problem=problem,
                    grade=session.get("grade", "3"),
                    language=session.get("language", "ko"),
                )
                session["coaching_questions"] = coaching_questions

        elif form_type == "answers":
            answers = {
                "when": request.form.get("answer_when", "").strip(),
                "who": request.form.get("answer_who", "").strip(),
                "why": request.form.get("answer_why", "").strip(),
            }
            session["answers"] = answers
            return redirect(url_for("direction"))

    return render_template(
        "question.html",
        topic=session.get("topic", WEEKLY_TOPIC),
        problem=session.get("problem", ""),
        coaching_questions=coaching_questions,
    )


@app.route("/direction", methods=["GET", "POST"])
def direction():
    if "problem" not in session or "answers" not in session:
        return redirect(url_for("question"))

    direction_data = session.get("direction_data")
    if not direction_data:
        direction_data = generate_invention_directions(
            problem=session["problem"],
            answers=session["answers"],
            grade=session.get("grade", "3"),
            language=session.get("language", "ko"),
        )
        session["direction_data"] = direction_data

    if request.method == "POST":
        session["chosen_direction"] = request.form.get("chosen_direction", "").strip()
        session["final_idea"] = request.form.get("final_idea", "").strip()
        return redirect(url_for("note"))

    return render_template(
        "direction.html",
        topic=session.get("topic", WEEKLY_TOPIC),
        problem=session.get("problem", ""),
        answers=session.get("answers", {}),
        direction_data=direction_data,
    )


@app.route("/note", methods=["GET", "POST"])
def note():
    if "final_idea" not in session:
        return redirect(url_for("direction"))

    note_summary = session.get("note_summary")
    if not note_summary:
        note_summary = generate_invention_note(
            topic=session.get("topic", WEEKLY_TOPIC),
            problem=session.get("problem", ""),
            answers=session.get("answers", {}),
            direction=session.get("chosen_direction", ""),
            final_idea=session.get("final_idea", ""),
        )
        session["note_summary"] = note_summary

    # Save once per student flow
    if not session.get("saved"):
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "grade": session.get("grade", ""),
            "language": session.get("language", ""),
            "topic": session.get("topic", ""),
            "problem": session.get("problem", ""),
            "when_happens": session.get("answers", {}).get("when", ""),
            "who_affected": session.get("answers", {}).get("who", ""),
            "why_happens": session.get("answers", {}).get("why", ""),
            "invention_directions": session.get("chosen_direction", ""),
            "final_idea": session.get("final_idea", ""),
            "note_summary": note_summary,
        }
        save_result_to_csv(record)
        session["saved"] = True

    if request.method == "POST":
        session.clear()
        return redirect(url_for("index"))

    return render_template(
        "note.html",
        topic=session.get("topic", WEEKLY_TOPIC),
        problem=session.get("problem", ""),
        answers=session.get("answers", {}),
        direction=session.get("chosen_direction", ""),
        final_idea=session.get("final_idea", ""),
        note_summary=note_summary,
    )


@app.route("/teacher")
def teacher():
    results = load_results_from_csv()
    return render_template("teacher.html", weekly_topic=WEEKLY_TOPIC, results=results)


if __name__ == "__main__":
    ensure_csv_file()
    app.run(debug=True)
