# app/init_db.py

from app.db.base import Base, engine
from app.db import models  # ensures all models are registered with Base

print("Creating tables...")
Base.metadata.create_all(bind=engine)
print("Done.")
