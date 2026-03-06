from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, Text
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
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    total_submissions = Column(Integer, default=0)
    rating = Column(Integer, default=1500)

    # Relationships
    problems = relationship("Problem", back_populates="author")
    submissions = relationship("Submission", back_populates="user")


class Problem(Base):
    """
    Top level problem entity. Contains the stable index of a problem mapping to its
    latest version or multiple historical versions.
    """
    __tablename__ = "problems"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False, unique=True)
    author_id = Column(Integer, ForeignKey("users.id"))
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    is_published = Column(Boolean, default=False)

    # Relationships
    author = relationship("User", back_populates="problems")
    versions = relationship("ProblemVersion", back_populates="problem", cascade="all, delete-orphan")


class ProblemVersion(Base):
    """
    Represents a specific snapshot of a problem: its description (markdown), 
    and resource constraints. Ensures submissions are judged against correct historical context.
    """
    __tablename__ = "problem_versions"

    id = Column(Integer, primary_key=True, index=True)
    problem_id = Column(Integer, ForeignKey("problems.id"), nullable=False)
    
    # Versioning info
    version_number = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Specification
    statement_url = Column(String, nullable=False)
    time_limit_ms = Column(Integer, default=2000)
    memory_limit_mb = Column(Integer, default=256)
    
    # Relative path reference to where the physical I/O test cases are stored 
    # (e.g., "/test_data/problem_1/v2")
    test_data_path = Column(String, nullable=False)

    # Relationships
    problem = relationship("Problem", back_populates="versions")
    submissions = relationship("Submission", back_populates="problem_version")
    test_cases = relationship("TestCase", back_populates="problem_version", cascade="all, delete-orphan")


class TestCase(Base):
    """
    Represents an individual I/O test case for a specific problem version.
    """
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, index=True)
    problem_version_id = Column(Integer, ForeignKey("problem_versions.id"), nullable=False)
    
    input_data = Column(Text, nullable=False)
    expected_output = Column(Text, nullable=False)
    
    is_sample = Column(Boolean, default=False)
    score = Column(Integer, default=10)

    problem_version = relationship("ProblemVersion", back_populates="test_cases")


class Submission(Base):
    """
    Submission History mapping every piece of code sent to the server.
    Tied directly to down to the granular ProblemVersion context.
    """
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    problem_version_id = Column(Integer, ForeignKey("problem_versions.id"), nullable=False)
    
    language = Column(String(20), nullable=False)
    code_url = Column(String, nullable=False)
    
    # Verdict/Statistics
    status = Column(String(20), default="PENDING")  # e.g., PENDING, AC, WA, CE, TLE, MLE, RE
    execution_time_ms = Column(Float, nullable=True)
    peak_memory_mb = Column(Float, nullable=True)
    
    # E.g callback tracking if needed
    callback_url = Column(String, nullable=True)
    
    submitted_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="submissions")
    problem_version = relationship("ProblemVersion", back_populates="submissions")
