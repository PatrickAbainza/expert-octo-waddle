import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase # Use DeclarativeBase class

# Use environment variable or default for database URL
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./inventory.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Using the modern SQLAlchemy 2.0 style
class Base(DeclarativeBase):
    pass

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Function to create tables (optional, can be called from main or a script)
def create_db_and_tables():
    Base.metadata.create_all(bind=engine)