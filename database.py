from sqlalchemy import create_engine, Column, String, Integer, Boolean, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

DATABASE_URL = "sqlite:///./student_assistant.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class TimetableEntry(Base):
    __tablename__ = "timetable"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, default="default")
    course_code = Column(String, nullable=False)
    course_name = Column(String, nullable=False)
    index_number = Column(String, nullable=False)
    class_type = Column(String)        # LEC, TUT, LAB, etc.
    group = Column(String)
    day = Column(String)               # MON, TUE, WED, THU, FRI, SAT
    time_start = Column(String)        # e.g. "0830"
    time_end = Column(String)          # e.g. "0930"
    venue = Column(String)
    remark = Column(String)
    academic_year = Column(String, default="2026;1")
    created_at = Column(DateTime, default=datetime.utcnow)


class TodoItem(Base):
    __tablename__ = "todos"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, default="default")
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    course_code = Column(String, default="")   # optional link to a course
    due_date = Column(String, default="")       # ISO date string
    is_done = Column(Boolean, default=False)
    priority = Column(String, default="medium") # low / medium / high
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
