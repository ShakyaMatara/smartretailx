from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from models import Base

# pool_pre_ping tests a pooled connection before handing it out.
# Without it, a connection dropped by the database (a failover,
# an idle timeout) surfaces as a random 500 on the next request.
# This is a small but genuine resilience measure.
engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create tables if they do not exist. Suitable for coursework;
    production would use Alembic migrations."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Yields a database session per request and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
