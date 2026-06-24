"""
Dify API client for generating daily revision schedule suggestions.
Configure DIFY_API_KEY and DIFY_BASE_URL in your .env file.
"""

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

DIFY_API_KEY = os.getenv("DIFY_API_KEY", "")
DIFY_BASE_URL = os.getenv("DIFY_BASE_URL", "https://api.dify.ai/v1")


def _headers():
    return {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }


def get_revision_suggestions(timetable: list[dict], todos: list[dict], user_id: str = "default") -> str:
    """
    Sends the student's timetable and todo list to Dify and returns
    a suggested daily revision schedule as a string.
    """
    if not DIFY_API_KEY:
        return "Dify API key not configured. Please set DIFY_API_KEY in your .env file."

    timetable_text = _format_timetable(timetable)
    todos_text = _format_todos(todos)

    prompt = (
        f"I am an NTU student. Here is my weekly class timetable:\n{timetable_text}\n\n"
        f"Here are my pending to-do items:\n{todos_text}\n\n"
        "Please suggest a realistic daily revision schedule for this week, "
        "taking into account my class timings and pending tasks. "
        "Prioritise high-priority tasks and spread revision sessions across free slots."
    )

    payload = {
        "inputs": {},
        "query": prompt,
        "response_mode": "blocking",
        "conversation_id": "",
        "user": user_id,
    }

    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{DIFY_BASE_URL}/chat-messages",
                headers=_headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("answer", "No suggestion returned.")
    except httpx.HTTPStatusError as e:
        return f"Dify API error {e.response.status_code}: {e.response.text}"
    except Exception as e:
        return f"Failed to reach Dify: {str(e)}"


def _format_timetable(entries: list[dict]) -> str:
    if not entries:
        return "No classes registered."
    lines = []
    for e in entries:
        lines.append(
            f"- {e['course_code']} {e['course_name']} | {e['class_type']} | "
            f"{e['day']} {e['time_start']}-{e['time_end']} | {e['venue']}"
        )
    return "\n".join(lines)


def _format_todos(todos: list[dict]) -> str:
    pending = [t for t in todos if not t.get("is_done")]
    if not pending:
        return "No pending to-do items."
    lines = []
    for t in pending:
        due = f" (due {t['due_date']})" if t.get("due_date") else ""
        lines.append(f"- [{t['priority'].upper()}] {t['title']}{due}: {t.get('description', '')}")
    return "\n".join(lines)
