from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=True, bind=engine)

Base = declarative_base()

# Dependency
def get_db():
    db = SessionLocal()  # create a new session
    try:
        yield db
        db.commit()  # Ensure the session is committed before closing
    except Exception as e:
        db.rollback()  # In case of any error, roll back the session
        raise e  # Reraise the exception to propagate the error
    finally:
        db.close()  # Always close the session
