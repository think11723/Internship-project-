"""
Resume model
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from app.db.session import Base


class Resume(Base):
    """Resume model for storing parsed resume data"""
    
    __tablename__ = "resumes"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=True)
    
    # Personal information
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    location = Column(String(255), nullable=True)
    
    # Analysis data
    summary = Column(Text, nullable=True)
    skills = Column(JSON, nullable=True)
    experience = Column(JSON, nullable=True)
    education = Column(JSON, nullable=True)
    projects = Column(JSON, nullable=True)
    certifications = Column(JSON, nullable=True)
    technologies = Column(JSON, nullable=True)
    strengths = Column(JSON, nullable=True)
    
    # Full analysis JSON
    analysis_json = Column(JSON, nullable=True)
    
    # Raw data
    raw_text = Column(Text, nullable=True)

    # File metadata
    file_size = Column(Integer, nullable=True)

    # Metadata
    parsed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<Resume(id={self.id}, filename='{self.original_filename}')>"
