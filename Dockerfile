FROM python:3.10-slim

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies (if required)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt first to leverage Docker caching
COPY requirements.txt .

# Install the Python dependencies from the requirements file
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project to the container
COPY . .

# Set environment variables for the app (these can be overridden in the Docker run command or in your cloud platform)
ENV PORT=8000
ENV DATABASE_URL=postgresql://neondb_owner:npg_SwdbrNq1QIi4@ep-withered-mouse-a40or4mx-pooler.us-east-1.aws.neon.tech/webhook-url?sslmode=require
ENV REDIS_URL=redis://redis:6379/0
ENV MAX_RETRY_ATTEMPTS=5
ENV LOG_RETENTION_HOURS=72

# Expose the port that Uvicorn will run on
EXPOSE 8000

# Start the application using Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
