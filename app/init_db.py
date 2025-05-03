# app/init_db.py
from app.db.base import Base, engine
from app.db import models  # This imports all your models

print("Dropping existing tables...")
Base.metadata.drop_all(bind=engine)  # Only for development!

print("Creating fresh tables...")
Base.metadata.create_all(bind=engine)
print("Database tables created successfully.")