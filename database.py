import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# Database URL - supports both SQLite and PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./billsplit.db")

# Connection arguments based on database type
connect_args = {}
engine_kwargs = {}

if "sqlite" in DATABASE_URL:
    connect_args = {"check_same_thread": False}
elif "postgresql" in DATABASE_URL:
    # PostgreSQL specific optimizations
    engine_kwargs = {
        "pool_size": 10,  # Number of connections to maintain
        "max_overflow": 20,  # Additional connections if pool is full
        "pool_pre_ping": True,  # Test connections before using
        "pool_recycle": 3600,  # Recycle connections after 1 hour
    }

# Create engine
engine = create_engine(
    DATABASE_URL, 
    connect_args=connect_args,
    **engine_kwargs
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class
Base = declarative_base()

def init_db():
    """Initialize database and create all tables"""
    from models import TelegramUser, Group, Expense, Split
    Base.metadata.create_all(bind=engine)
    print(f"Database initialized: {DATABASE_URL}")

def get_db():
    """Dependency for FastAPI to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()