from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import Config

engine = create_engine(Config.SQLALCHEMY_DATABASE_URI, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()