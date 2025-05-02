# Webhook Delivery Service

A reliable webhook delivery service that ingests incoming webhooks, queues them, and delivers them to target URLs with retry capabilities.

## Features

- Subscription management (CRUD operations)
- Webhook ingestion and asynchronous delivery
- Automatic retries with exponential backoff
- Comprehensive delivery logging
- Analytics endpoints for monitoring

## Technology Stack

- **Backend**: Python with FastAPI
- **Database**: PostgreSQL
- **Queue/Cache**: Redis + Celery
- **Containerization**: Docker + Docker Compose

## Setup and Installation

### Prerequisites

- Docker and Docker Compose

### Running Locally

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd webhook-service