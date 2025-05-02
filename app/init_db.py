# app/init_db.py
from app.db.base import Base, engine
from app.db import models  # import your models so they register

def init():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init()
