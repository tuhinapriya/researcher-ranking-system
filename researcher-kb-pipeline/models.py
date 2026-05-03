from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Text,
    ForeignKey,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Institution(Base):
    __tablename__ = "institutions"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    country = Column(String)
    prestige_tag = Column(String)
    h_index = Column(Integer)
    total_citations = Column(Integer)
    region = Column(String)

    researchers = relationship("Researcher", back_populates="current_institution")


class Researcher(Base):
    __tablename__ = "researchers"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    total_works = Column(Integer)
    total_citations = Column(Integer)
    h_index = Column(Integer)
    i10_index = Column(Integer)
    years_active = Column(Integer)
    current_institution_id = Column(String, ForeignKey("institutions.id"))
    country = Column(String)
    last_author_ratio_recent = Column(Float)
    industry_collaboration_score = Column(Float)
    quality_score = Column(Float)
    recency_score = Column(Float)
    last_updated = Column(DateTime)

    current_institution = relationship("Institution", back_populates="researchers")
    papers = relationship("Paper", back_populates="researcher")


class Paper(Base):
    __tablename__ = "papers"

    id = Column(String, primary_key=True)
    researcher_id = Column(String, ForeignKey("researchers.id"), index=True)
    title = Column(String, nullable=False)
    year = Column(Integer, index=True)
    venue = Column(String)
    venue_type = Column(String)
    citations = Column(Integer)
    concept = Column(String)
    abstract = Column(Text)
    embedding_id = Column(String, index=True)

    researcher = relationship("Researcher", back_populates="papers")
