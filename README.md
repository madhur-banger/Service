# Webhook Delivery Service

A robust backend system built with **FastAPI** and **Celery** to ingest, queue, and reliably deliver webhook events with retries, logging, caching, and analytics — fully containerized using **Docker Compose**.

---

##  Features

-  CRUD for Webhook Subscriptions
-  Webhook Ingestion with Queuing
-  Asynchronous Delivery with Celery + Redis
-  Retry with Exponential Backoff
-  Delivery Logs and Analytics
-  Log Retention (72 hours)
-  Swagger UI for API Interaction
-  Dockerized Deployment
-  Tested for 500 requests with 100 concurrent users

---

##  Tech Stack

| Component        | Tech Used            |
|------------------|----------------------|
| Backend API      | FastAPI              |
| Async Tasks      | Celery               |
| Message Broker   | Redis                |
| Database         | PostgreSQL (NeonDB)  |
| Caching          | Redis                |
| Containerization | Docker,Docker Compose|
| Deployment       | Render               |
| Testing          | Pytest               |

---

##  Project Structure

```

app/
├── api/
│   ├── analytics.py
│   ├── subscriptions.py
│   ├── webhooks.py
│   └── router.py
├── core/
├── db/
│   ├── base.py
│   ├── crud.py
│   └── models.py
├── schemas/
├── tasks/
│   ├── cleanup.py
│   ├── delivery.py
│   └── worker.py
├── main.py
├── init\_db.py
├── static/
tests/
├── test\_subscription.py
├── test\_webhook.py
Dockerfile
docker-compose.yml
requirements.txt
README.md

````

---

##  Local Setup (via Docker)

###  Prerequisites

- Docker & Docker Compose installed
- Ports `8000`, `5432`, and `6379` available

##  Run the app

### Clone the repo

```bash
git clone https://github.com/madhur-banger/Service
cd service
```

### Build and start containers
```bash
docker-compose up --build
```


* API available at: `http://localhost:8000`
* Swagger UI: `http://localhost:8000/docs`

---

##  API Endpoints

All routes are prefixed with `/api`.

###  Subscriptions

| Method | Endpoint                                       | Description                      |
| ------ | ---------------------------------------------- | -------------------------------- |
| POST   | `/subscriptions/`                              | Create a subscription            |
| GET    | `/subscriptions/`                              | List all subscriptions           |
| GET    | `/subscriptions/{subscription_id}`             | Retrieve a specific subscription |
| PUT    | `/subscriptions/{subscription_id}`             | Update a subscription            |
| DELETE | `/subscriptions/{subscription_id}`             | Delete a subscription            |
| PUT    | `/subscriptions/{subscription_id}/event-types` | Update event types               |

### Webhooks

| Method | Endpoint                                                | Description                              |
| ------ | ------------------------------------------------------- | ---------------------------------------- |
| POST   | `/webhooks/ingest/{subscription_id}`                    | Ingest webhook for specific subscription |
| POST   | `/webhooks/ingest`                                      | Ingest to all subscriptions              |
| PUT    | `/webhooks/subscriptions/{subscription_id}/event-types` | Update subscription events               |

###  Analytics

| Method | Endpoint                                                | Description           |
| ------ | ------------------------------------------------------- | --------------------- |
| GET    | `/analytics/deliveries/{delivery_id}`                   | Get delivery status   |
| GET    | `/analytics/subscriptions/{subscription_id}/deliveries` | Get recent deliveries |
| GET    | `/analytics/subscriptions/{subscription_id}/attempts`   | Get recent attempts   |

---

##  Architecture Choices

| Component      | Choice              | Rationale                                     |
| -------------- | ------------------- | --------------------------------------------- |
| **Framework**  | FastAPI             | Async-native, fast, built-in Swagger          |
| **Database**   | PostgreSQL (NeonDB) | Reliable SQL, supports indexing & JSON        |
| **Async**      | Celery + Redis      | Reliable task queue with retry logic          |
| **Containers** | Docker              | Easy to replicate and deploy                  |
| **Workers**    | 2 FastAPI, 4 Celery | Scaled concurrency for ingestion and delivery |

---

##  Sample Usage (cURL)

###  Create Subscription

---

### 1. Create Subscription

```bash
curl -X POST http://localhost:8000/api/subscriptions/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "string",
    "target_url": "https://webhook.site/62c2b6c8-7dc7-4087-b3f8-0d38dbd15bcd",
    "secret_key": "string"
  }'
```

---

### 2. Read Subscriptions (List)

```bash
curl -X GET "http://localhost:8000/api/subscriptions/?skip=0&limit=100" \
  -H "accept: application/json"
```

---

### 3. Read Subscription (by ID)

```bash
curl -X GET http://localhost:8000/api/subscriptions/{subscription_id} \
  -H "accept: application/json"
```

*Replace `{subscription_id}` with the actual UUID.*

---

### 4. Update Subscription (by ID)

```bash
curl -X PUT http://localhost:8000/api/subscriptions/{subscription_id} \
  -H "Content-Type: application/json" \
  -d '{
    "name": "string",
    "target_url": "https://example.com/",
    "secret_key": "string",
    "is_active": true
  }'
```

*Replace `{subscription_id}` with the actual UUID.*

---

### 5. Delete Subscription (by ID)

```bash
curl -X DELETE http://localhost:8000/api/subscriptions/{subscription_id} \
  -H "accept: application/json"
```

*Replace `{subscription_id}` with the actual UUID.*

---

### 6. Update Subscription Event Types

```bash
curl -X PUT http://localhost:8000/api/subscriptions/subscriptions/{subscription_id}/event-types \
  -H "Content-Type: application/json" \
  -d '[
    "event_type_1",
    "event_type_2"
  ]'
```

*Replace `{subscription_id}` with actual UUID.*

---

### 7. Ingest Webhook for Subscription

```bash
curl -X POST "http://localhost:8000/api/webhooks/ingest/{subscription_id}?event_type=order.created" \
  -H "Content-Type: application/json" \
  -d '{}'
```

*Replace `{subscription_id}` with actual UUID and `event_type` as needed.*

---

### 8. Ingest Webhook To All

```bash
curl -X POST "http://localhost:8000/api/webhooks/ingest?event_type=order.created" \
  -H "Content-Type: application/json" \
  -d '{}'
```

---

### 9. Get Delivery Status (by delivery\_id)

```bash
curl -X GET http://localhost:8000/api/analytics/deliveries/{delivery_id} \
  -H "accept: application/json"
```

*Replace `{delivery_id}` with actual UUID.*



---

##  Cost Estimation (Free Tier)

Assuming deployment on **Render Free Tier** or **Railway**:

* API service: Free (limited hours or autosleep)
* PostgreSQL: Free Tier (NeonDB)
* Redis: Free Tier (Upstash or Redis Cloud)
* Estimated Cost: **\$0/month** for light usage

> Handles \~5000 webhooks/day with \~1.2 attempts/webhook = 6000 deliveries

---

##  Database Schema ing

### `subscriptions` table

| Field       | Type      | 
| ----------- | --------- | 
| id          | UUID      | 
| target\_url | TEXT      | 
| secret      | TEXT      | 
| created\_at | TIMESTAMP | 

### `delivery_logs` table

| Field            | Type      | 
| ---------------- | --------- |
| id               | UUID      | 
| subscription\_id | UUID      | 
| delivery\_status | TEXT      | 
| attempt\_num     | INTEGER   | 
| created\_at      | TIMESTAMP | 



---

##  Retry Strategy

* **Initial Retry**: After 10s
* **Backoff Steps**: 10s → 30s → 1m → 5m → 15m
* **Max Attempts**: 5
* **Failure**: Marked after all retries fail
* **Timeout per request**: 5–10 seconds

---

##  Log Retention Policy

* All delivery logs are stored with timestamps
* A periodic Celery task runs every hour to purge logs older than **72 hours**

---

##  Assumptions

* Ingested webhook JSONs are schema-less (flexible)
* Target URLs are assumed to accept `POST` with JSON
* No authentication required for internal APIs (for testing/demo)

---

##  Credits

* [FastAPI](https://fastapi.tiangolo.com/)
* [Celery](https://docs.celeryq.dev/en/stable/)
* [Redis](https://redis.io/)
* [NeonDB](https://neon.tech/)
* [Docker](https://docker.com/)
* AI Help: ChatGPT by OpenAI (for formatting, examples, retry logic)