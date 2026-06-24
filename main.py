from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import uvicorn

from database import init_db, get_db, TimetableEntry, TodoItem
from scraper import fetch_schedule_by_course_code, fetch_schedule_by_index, search_by_keyword
from dify_client import get_revision_suggestions


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="NTU Student Assistant", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class TimetableEntryCreate(BaseModel):
    course_code: str
    course_name: str
    index_number: str
    class_type: str = ""
    group: str = ""
    day: str = ""
    time_start: str = ""
    time_end: str = ""
    venue: str = ""
    remark: str = ""
    academic_year: str = "2026;1"
    user_id: str = "default"


class TodoCreate(BaseModel):
    title: str
    description: str = ""
    course_code: str = ""
    due_date: str = ""
    priority: str = "medium"
    user_id: str = "default"


class TodoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    course_code: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[str] = None
    is_done: Optional[bool] = None


# ── Schedule lookup (WISH scraper) ────────────────────────────────────────────

@app.get("/api/schedule/search")
def search_by_name(keyword: str, acad_year: str = "2025;2"):
    """Search courses by keyword in module name, e.g. 'calculus', 'data science'."""
    try:
        courses = search_by_keyword(keyword, acad_year)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"WISH fetch failed: {e}")
    if not courses:
        raise HTTPException(status_code=404, detail="No courses found for this keyword.")
    return {"keyword": keyword, "courses": courses}


@app.get("/api/schedule/course/{course_code}")
def search_by_course(course_code: str, acad_year: str = "2025;2"):
    """Search NTU WISH by course code, e.g. SC1003."""
    try:
        slots = fetch_schedule_by_course_code(course_code, acad_year)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"WISH fetch failed: {e}")
    if not slots:
        raise HTTPException(status_code=404, detail="No schedule found for this course code.")
    return {"course_code": course_code.upper(), "slots": slots}


@app.get("/api/schedule/index/{course_code}/{index_number}")
def search_by_index(course_code: str, index_number: str, acad_year: str = "2025;2"):
    """Filter slots for a specific index number within a course, e.g. SC1003/10001."""
    try:
        slots = fetch_schedule_by_index(course_code, index_number, acad_year)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"WISH fetch failed: {e}")
    if not slots:
        raise HTTPException(status_code=404, detail="No schedule found for this index number.")
    return {"course_code": course_code.upper(), "index_number": index_number, "slots": slots}


# ── Timetable CRUD ────────────────────────────────────────────────────────────

@app.get("/api/timetable")
def get_timetable(user_id: str = "default", db: Session = Depends(get_db)):
    entries = db.query(TimetableEntry).filter(TimetableEntry.user_id == user_id).all()
    return entries


@app.post("/api/timetable", status_code=201)
def add_timetable_entry(entry: TimetableEntryCreate, db: Session = Depends(get_db)):
    db_entry = TimetableEntry(**entry.model_dump())
    db.add(db_entry)
    db.commit()
    db.refresh(db_entry)
    return db_entry


@app.post("/api/timetable/from-wish", status_code=201)
def add_from_wish(course_code: str, index_number: str, acad_year: str = "2025;2",
                  user_id: str = "default", db: Session = Depends(get_db)):
    """
    Fetch all slots for a course+index from WISH and save them to the timetable.
    Students first search /api/schedule/course/{code} to find their index, then call this.
    """
    try:
        slots = fetch_schedule_by_index(course_code, index_number, acad_year)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"WISH fetch failed: {e}")
    if not slots:
        raise HTTPException(status_code=404, detail="No schedule found for this index number.")

    saved = []
    for slot in slots:
        db_entry = TimetableEntry(user_id=user_id, academic_year=acad_year, **slot)
        db.add(db_entry)
        saved.append(db_entry)
    db.commit()
    for s in saved:
        db.refresh(s)
    return {"added": len(saved), "entries": saved}


@app.delete("/api/timetable/{entry_id}", status_code=204)
def delete_timetable_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(TimetableEntry).filter(TimetableEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found.")
    db.delete(entry)
    db.commit()


# ── Todo CRUD ─────────────────────────────────────────────────────────────────

@app.get("/api/todos")
def get_todos(user_id: str = "default", db: Session = Depends(get_db)):
    return db.query(TodoItem).filter(TodoItem.user_id == user_id).all()


@app.post("/api/todos", status_code=201)
def create_todo(todo: TodoCreate, db: Session = Depends(get_db)):
    db_todo = TodoItem(**todo.model_dump())
    db.add(db_todo)
    db.commit()
    db.refresh(db_todo)
    return db_todo


@app.patch("/api/todos/{todo_id}")
def update_todo(todo_id: int, updates: TodoUpdate, db: Session = Depends(get_db)):
    todo = db.query(TodoItem).filter(TodoItem.id == todo_id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found.")
    for field, value in updates.model_dump(exclude_none=True).items():
        setattr(todo, field, value)
    db.commit()
    db.refresh(todo)
    return todo


@app.delete("/api/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: int, db: Session = Depends(get_db)):
    todo = db.query(TodoItem).filter(TodoItem.id == todo_id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found.")
    db.delete(todo)
    db.commit()


# ── Index suggestions (clash detection) ──────────────────────────────────────

@app.get("/api/schedule/suggest/{course_code}")
def suggest_indexes(course_code: str, user_id: str = "default",
                    acad_year: str = "2025;2", db: Session = Depends(get_db)):
    """
    Returns all indexes for a course, each marked as CLASH or FREE
    based on the student's existing timetable.
    """
    try:
        all_slots = fetch_schedule_by_course_code(course_code, acad_year)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"WISH fetch failed: {e}")
    if not all_slots:
        raise HTTPException(status_code=404, detail="No schedule found for this course code.")

    # Get student's existing timetable
    existing = db.query(TimetableEntry).filter(TimetableEntry.user_id == user_id).all()
    existing_slots = {(e.day, e.time_start, e.time_end) for e in existing}

    # Group slots by index number
    indexes: dict[str, dict] = {}
    for slot in all_slots:
        idx = slot["index_number"]
        if idx not in indexes:
            indexes[idx] = {"slots": [], "clashes": []}
        indexes[idx]["slots"].append(slot)
        if (slot["day"], slot["time_start"], slot["time_end"]) in existing_slots:
            indexes[idx]["clashes"].append(slot)

    result = []
    for idx, data in indexes.items():
        result.append({
            "index_number": idx,
            "status": "CLASH" if data["clashes"] else "FREE",
            "clash_details": data["clashes"],
            "slots": data["slots"],
        })

    return {
        "course_code": course_code.upper(),
        "course_name": all_slots[0]["course_name"] if all_slots else "",
        "indexes": result,
    }


# ── Dify revision suggestions ─────────────────────────────────────────────────

@app.get("/api/suggestions")
def get_suggestions(user_id: str = "default", db: Session = Depends(get_db)):
    """Ask Dify to generate a weekly revision plan based on timetable + todos."""
    timetable = db.query(TimetableEntry).filter(TimetableEntry.user_id == user_id).all()
    todos = db.query(TodoItem).filter(TodoItem.user_id == user_id).all()

    timetable_dicts = [
        {
            "course_code": e.course_code,
            "course_name": e.course_name,
            "class_type": e.class_type,
            "day": e.day,
            "time_start": e.time_start,
            "time_end": e.time_end,
            "venue": e.venue,
        }
        for e in timetable
    ]
    todo_dicts = [
        {
            "title": t.title,
            "description": t.description,
            "course_code": t.course_code,
            "due_date": t.due_date,
            "priority": t.priority,
            "is_done": t.is_done,
        }
        for t in todos
    ]

    suggestion = get_revision_suggestions(timetable_dicts, todo_dicts, user_id)
    return {"suggestion": suggestion}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
