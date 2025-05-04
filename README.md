Absolutely! Here's a **detailed, production-quality `README.md`** in proper **Markdown format** for your **Webhook Delivery Service** project. It covers all deliverables: setup, architecture, APIs, deployment, and more — cleanly formatted and ready to go.

---


  Webhook Delivery Service

A robust backend system built with FastAPI** and **Celery** to ingest, queue, and reliably deliver webhook events with retries, logging, caching, and analytics — fully containerized using **Docker Compose**.

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

###  Run the app

# Clone the repo

```bash
git clone https://github.com/madhur-banger/Service
cd service
```
```

# Build and start containers
docker-compose up --build


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

```bash
curl -X POST http://localhost:8000/api/subscriptions/ \
-H "Content-Type: application/json" \
-d '{
  "target_url": "https://example.com/webhook",
  "secret": "super-secret-key"
}'
```

###  Ingest Webhook

```bash
curl -X POST http://localhost:8000/api/webhooks/ingest/{subscription_id} \
-H "Content-Type: application/json" \
-d '{"event": "user.signup", "data": {"user_id": 123}}'
```

### 📈 Get Delivery Logs

```bash
curl http://localhost:8000/api/analytics/subscriptions/{subscription_id}/deliveries
```

---

## 💸 Cost Estimation (Free Tier)

Assuming deployment on **Render Free Tier** or **Railway**:

* API service: Free (limited hours or autosleep)
* PostgreSQL: Free Tier (NeonDB)
* Redis: Free Tier (Upstash or Redis Cloud)
* Estimated Cost: **\$0/month** for light usage

> Handles \~5000 webhooks/day with \~1.2 attempts/webhook = 6000 deliveries

---

## 🗃️ Database Schema ing

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

## 🔁 Retry Strategy

* **Initial Retry**: After 10s
* **Backoff Steps**: 10s → 30s → 1m → 5m → 15m
* **Max Attempts**: 5
* **Failure**: Marked after all retries fail
* **Timeout per request**: 5–10 seconds

---

## 🧹 Log Retention Policy

* All delivery logs are stored with timestamps
* A periodic Celery task runs every hour to purge logs older than **72 hours**

---

## 🌐 Deployment

> 📍 Replace with actual live URL

* **Live App**: [https://your-app.onrender.com](https://your-app.onrender.com)
* Accessible via Swagger UI and minimal HTML UI

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

---

##  Contributors

* [Madhur Banger](https://github.com/madhur-banger)

---

##  Questions?

For inquiries or issues, reach out via [GitHub](https://github.com/madhur-banger) or email: [madhur.cloudevops@gmail.com](mailto:madhur.cloudevops@gmail.com)

```

---

Let me know if you’d like a matching `docker-compose.yml` section, architecture diagram, or Swagger screenshot added.
```
