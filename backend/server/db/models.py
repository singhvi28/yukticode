from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
import datetime

from server.db.database import Base


class User(Base):
    """
    User model for storing profiles, hashed passwords, and permissions.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    problems = relationship("Problem", back_populates="author")
    submissions = relationship("Submission", back_populates="user")
    contests_created = relationship("Contest", back_populates="creator")


class Problem(Base):
    """
    A problem with its statement, resource limits, and test cases.
    """
    __tablename__ = "problems"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False, unique=True)
    author_id = Column(Integer, ForeignKey("users.id"))

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))
    is_published = Column(Boolean, default=False)

    difficulty = Column(String(20), default="Medium")
    tags = Column(String, default="[]")  # Stored as JSON string

    statement = Column(Text, nullable=False, default="")
    time_limit_ms = Column(Integer, default=2000)
    memory_limit_mb = Column(Integer, default=256)

    # Relationships
    author = relationship("User", back_populates="problems")
    submissions = relationship("Submission", back_populates="problem")
    test_cases = relationship("TestCase", back_populates="problem", cascade="all, delete-orphan")


class TestCase(Base):
    """
    An individual I/O test case for a problem.
    """
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, index=True)
    problem_id = Column(Integer, ForeignKey("problems.id"), nullable=False)

    input_data = Column(Text, nullable=False)
    expected_output = Column(Text, nullable=False)

    is_sample = Column(Boolean, default=False)
    score = Column(Integer, default=10)

    problem = relationship("Problem", back_populates="test_cases")


class Submission(Base):
    """
    Submission history for a problem.
    """
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    problem_id = Column(Integer, ForeignKey("problems.id"), nullable=False)

    language = Column(String(20), nullable=False)
    code = Column(Text, nullable=False)

    # Verdict/Statistics
    status = Column(String(20), default="PENDING")  # e.g., PENDING, AC, WA, CE, TLE, MLE, RE
    execution_time_ms = Column(Float, nullable=True)
    peak_memory_mb = Column(Float, nullable=True)

    submitted_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # If set, this submission counts toward the contest leaderboard.
    contest_id = Column(Integer, ForeignKey("contests.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    user = relationship("User", back_populates="submissions")
    problem = relationship("Problem", back_populates="submissions")


class Contest(Base):
    """
    A competitive contest grouping problems within a fixed time window.
    """
    __tablename__ = "contests"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(150), nullable=False, unique=True)
    description = Column(Text, default="")

    start_time = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)

    is_published = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))

    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Relationships
    creator = relationship("User", back_populates="contests_created")
    contest_problems = relationship("ContestProblem", back_populates="contest", cascade="all, delete-orphan")
    registrations = relationship("ContestRegistration", back_populates="contest", cascade="all, delete-orphan")


class ContestRegistration(Base):
    """Tracks which users have registered for a contest."""
    __tablename__ = "contest_registrations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    contest_id = Column(Integer, ForeignKey("contests.id", ondelete="CASCADE"), nullable=False)
    registered_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))

    user = relationship("User", backref="contest_registrations")
    contest = relationship("Contest", back_populates="registrations")


class ContestProblem(Base):
    """
    Associates a problem with a contest, recording its display order and score weight.
    """
    __tablename__ = "contest_problems"
    __table_args__ = (UniqueConstraint("contest_id", "problem_id", name="uq_contest_problem"),)

    id = Column(Integer, primary_key=True, index=True)
    contest_id = Column(Integer, ForeignKey("contests.id"), nullable=False)
    problem_id = Column(Integer, ForeignKey("problems.id"), nullable=False)

    score = Column(Integer, default=100)
    display_order = Column(Integer, default=0)

    # Relationships
    contest = relationship("Contest", back_populates="contest_problems")
    problem = relationship("Problem")
