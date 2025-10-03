from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Generator

from sqlalchemy import (
	Column,
	DateTime,
	ForeignKey,
	Integer,
	MetaData,
	String,
	Text,
	create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, Session, sessionmaker
from sqlalchemy import event
from sqlalchemy.pool import NullPool
import threading

from .config import settings


NAMING_CONVENTION = {
	"ix": "ix_%(column_0_label)s",
	"uq": "uq_%(table_name)s_%(column_0_name)s",
	"ck": "ck_%(table_name)s_%(constraint_name)s",
	"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
	"pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)
Base = declarative_base(metadata=metadata)

# Global write lock to serialize SQLite writes and avoid 'database is locked'
db_write_lock = threading.RLock()


def get_engine():
	url = settings.database_url
	if url.startswith("sqlite"):
		engine = create_engine(
			url,
			pool_pre_ping=True,
			future=True,
			poolclass=NullPool,
			connect_args={
				"check_same_thread": False,
				"timeout": 30,
			},
		)
		# Set WAL mode and busy timeout for better concurrency
		@event.listens_for(engine, "connect")
		def set_sqlite_pragma(dbapi_connection, connection_record):
			cursor = dbapi_connection.cursor()
			try:
				cursor.execute("PRAGMA journal_mode=WAL;")
				cursor.execute("PRAGMA synchronous=NORMAL;")
				cursor.execute("PRAGMA busy_timeout=5000;")
			finally:
				cursor.close()
		return engine
	return create_engine(url, pool_pre_ping=True, future=True)


engine = get_engine()
SessionLocal = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)


class Case(Base):
	__tablename__ = "cases"

	id = Column(Integer, primary_key=True)
	url = Column(String(1000), unique=True, nullable=False)
	court = Column(String(255))
	case_number = Column(String(255))
	parties = Column(String(1000))
	judges = Column(String(1000))
	date = Column(String(64))
	citation = Column(String(255))
	title = Column(String(1000))
	summary = Column(Text)
	content_text = Column(Text)
	created_at = Column(DateTime, default=datetime.utcnow)
	updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

	documents = relationship("Document", back_populates="case", cascade="all, delete-orphan")
	images = relationship("Image", back_populates="case", cascade="all, delete-orphan")


class Document(Base):
	__tablename__ = "documents"

	id = Column(Integer, primary_key=True)
	case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
	file_path = Column(String(2000), nullable=False)
	url = Column(String(1000))
	content_type = Column(String(255))
	created_at = Column(DateTime, default=datetime.utcnow)

	case = relationship("Case", back_populates="documents")


class Image(Base):
	__tablename__ = "images"

	id = Column(Integer, primary_key=True)
	case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
	file_path = Column(String(2000), nullable=False)
	url = Column(String(1000))
	alt_text = Column(String(1000))
	created_at = Column(DateTime, default=datetime.utcnow)

	case = relationship("Case", back_populates="images")


def init_db() -> None:
	Base.metadata.create_all(bind=engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
	session = SessionLocal()
	try:
		yield session
		session.commit()
	except Exception:
		session.rollback()
		raise
	finally:
		session.close()


