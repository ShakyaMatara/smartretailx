# SmartRetailX

A cloud-native, event-driven microservices platform built for **COMP60010 —
Enterprise Cloud and Distributed Web Applications**, assignment ECDWA2.

SmartRetailX decomposes a monolithic retail application into six independently
deployable services communicating over REST and an asynchronous event bus, with
distributed transaction handling, JWT-based security, and a deployment path to
Amazon Web Services.

---

## Contents

- [Architecture](#architecture)
- [Services](#services)
- [Technology choices](#technology-choices)
- [Running locally](#running-locally)
- [API documentation](#api-documentation)
- [Testing](#testing)
- [Performance testing](#performance-testing)
- [AWS deployment](#aws-deployment)
- [Repository layout](#repository-layout)
- [Design decisions](#design-decisions)
- [Known limitations](#known-limitations)

---

## Architecture

Six services, each owning its own datastore. No service reads another
service's database; all cross-service data access goes through APIs or events.

```
                    ┌──────────────┐
   Client ────────▶ │ User Service │ ── PostgreSQL (user-db)
                    └──────┬───────┘
                           │ publishes JWKS
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌───────────────┐  ┌──────────────┐  ┌─────────────────┐
│   Catalogue   │  │    Order     │  │    Inventory    │
│   DynamoDB    │◀─│  PostgreSQL  │  │    DynamoDB     │
└───────────────┘  └──────┬───────┘  └────────┬────────┘
                          │                   │
                    ┌─────▼───────────────────▼─────┐
                    │   SNS topic → 5 SQS queues    │
                    │   (each with a dead-letter Q) │
                    └─────┬───────────────────┬─────┘
                          │                   │
                  ┌───────▼──────┐   ┌────────▼─────────┐
                  │   Payment    │   │  Notification    │
                  │  PostgreSQL  │   │  WebSocket push  │
                  └──────────────┘   └──────────────────┘
```

**Synchronous** communication is used only where a caller needs an immediate
answer: the Order Service fetches product details from the Catalogue Service
over HTTP, protected by a retry policy and a circuit breaker.

**Asynchronous** communication carries everything else. Services publish domain
events to an SNS topic; SNS fans out to per-service SQS queues using
message-attribute filter policies, so each service receives only the event
types it handles.

### Order placement saga

Placing an order spans three services and cannot be wrapped in a single
database transaction. It is implemented as an orchestrated saga with
compensating transactions:

| Step | Service | Event published |
|------|---------|-----------------|
| 1 | Order — persist as `PENDING` | `OrderCreated` |
| 2 | Inventory — conditional stock decrement | `StockReserved` / `StockInsufficient` |
| 3 | Order — request payment | `PaymentRequested` |
| 4 | Payment — call gateway | `PaymentSucceeded` / `PaymentFailed` |
| 5a | Order — success | `OrderConfirmed` |
| 5b | Order — **compensate**: release stock, cancel | `StockReleased`, `OrderCancelled` |

Step 5b is the compensating transaction. There is no distributed rollback:
each completed step is reversed by an explicit compensating action published
as an event.

---

## Services

| Service | Port | Datastore | Responsibility |
|---------|------|-----------|----------------|
| user-service | 8001 | PostgreSQL | Registration, OAuth 2.0 login, JWT issuance, RBAC, GDPR erasure |
| catalogue-service | 8002 | DynamoDB | Product CRUD, category-indexed search, pricing |
| order-service | 8003 | PostgreSQL | Order placement, saga orchestration, idempotency |
| inventory-service | 8004 | DynamoDB | Stock reservation and release |
| payment-service | 8005 | PostgreSQL | Payment processing, PCI-DSS scope minimisation |
| notification-service | 8006 | none | Event fan-out to browsers over WebSocket |

Every service exposes `/health/live` and `/health/ready`. Liveness answers
"is the process alive"; readiness additionally verifies datastore
connectivity, so a service that is running but cannot reach its database
reports as not ready and is removed from rotation rather than failing
requests.

---

## Technology choices

| Choice | Rationale | Alternative rejected |
|--------|-----------|---------------------|
| **FastAPI** | Generates an OpenAPI 3.1 specification from route definitions and type annotations, so documentation cannot drift from implementation | Flask — would require hand-maintained specs |
| **Polyglot persistence** | PostgreSQL for relational order and payment data requiring transactional integrity; DynamoDB for key-based, read-heavy catalogue and stock lookups | A single database for all services — would couple services through a shared schema |
| **SNS + SQS** | Managed fan-out with subscription filter policies and dead-letter queues built in; no broker to operate | Apache Kafka / Amazon MSK — operational overhead and cost unjustified at this scale |
| **RS256 JWT** | Only the User Service holds the private key; other services verify using the public key published at `/.well-known/jwks.json`, with no shared secret distributed | HS256 — a shared secret means any service that can verify a token can also forge one |
| **Argon2id** | Current OWASP recommendation; memory-hard (64 MB, 3 iterations) so offline brute-force remains expensive | bcrypt — not memory-hard, cheaper to attack with GPUs |
| **ECS Fargate** | No control-plane fee, no cluster to manage | Amazon EKS — $0.10/hour control plane regardless of workload |
| **LocalStack** | Application code calls the real AWS SDK against a local endpoint, so the same image runs unchanged against managed AWS services | Mocking boto3 — would not exercise the real SDK code path |

---

## Running locally

### Prerequisites

- Docker Desktop
- Python 3.12+ (for the test suites)
- A free LocalStack account for an auth token — see below

### 1. Environment file

Copy the template and fill in values:

```powershell
Copy-Item .env.example .env
```

`.env` requires:

```
USER_DB_USER=smartretailx
USER_DB_PASSWORD=<choose one>
USER_DB_NAME=userdb

ORDER_DB_USER=smartretailx
ORDER_DB_PASSWORD=<choose one>
ORDER_DB_NAME=orderdb

PAYMENT_DB_USER=smartretailx
PAYMENT_DB_PASSWORD=<choose one>
PAYMENT_DB_NAME=paymentdb

LOCALSTACK_AUTH_TOKEN=<from app.localstack.cloud>
```

As of the LocalStack 2026.03 release the previously free community image was
consolidated into a single authenticated image. A free non-commercial tier is
available at `https://app.localstack.cloud`; register and copy the auth token.

### 2. JWT signing keys

The User Service signs tokens with an RSA private key, mounted read-only at
runtime and never baked into the image:

```powershell
mkdir keys
docker run --rm -v "${PWD}/keys:/keys" alpine/openssl genrsa -out /keys/jwt-private.pem 2048
docker run --rm -v "${PWD}/keys:/keys" alpine/openssl rsa -in /keys/jwt-private.pem -pubout -out /keys/jwt-public.pem
docker run --rm -v "${PWD}/keys:/keys" alpine sh -c "chmod 640 /keys/jwt-private.pem"
```

`keys/` is gitignored. The private key must never be committed.

### 3. Start the stack

```powershell
docker compose up --build -d
docker compose ps
```

Ten containers should report `healthy`: six services, three PostgreSQL
instances, and LocalStack.

### 4. Create an administrator

Roles are assigned by the server and never accepted from client input, so the
first administrator is promoted directly in the database:

```powershell
# Register through Swagger at http://localhost:8001/docs, then:
docker compose exec user-db psql -U smartretailx -d userdb `
  -c "UPDATE users SET role='admin' WHERE email='you@example.com';"
```

### 5. Live event stream

Open **http://localhost:8006** to watch domain events arrive in real time over
WebSocket as orders are placed.

---

## API documentation

Interactive Swagger UI is served by every service at `/docs`:

| Service | Swagger |
|---------|---------|
| User | http://localhost:8001/docs |
| Catalogue | http://localhost:8002/docs |
| Order | http://localhost:8003/docs |
| Inventory | http://localhost:8004/docs |
| Payment | http://localhost:8005/docs |
| Notification | http://localhost:8006/docs |

Exported OpenAPI 3.1 specifications are committed under `api-specs/` so the
contract can be reviewed without running the stack. Regenerate them with:

```powershell
.\scripts\export-specs.ps1
```

### API conventions

- **Versioning** — every business route is prefixed `/api/v1/`, allowing
  non-breaking evolution alongside a future `/api/v2/`.
- **Status codes** — `201` on create, `204` on delete, `409` on conflict,
  `422` on validation failure, `403` where the caller is authenticated but
  lacks the required role, `401` where identity cannot be established.
- **Pagination** — list endpoints take `limit` and `offset`, bounded server-side.
- **Idempotency** — `POST /api/v1/orders` requires an `Idempotency-Key`
  header. Resubmitting the same key returns the original order rather than
  placing a second one.
- **Correlation** — an `X-Correlation-ID` header is accepted or generated at
  the edge, propagated through every synchronous call and every published
  event, and returned to the caller.

---

## Testing

85 tests across five layers. Requires the stack to be running.

```powershell
pip install -r tests/requirements-test.txt
pytest
```

| Layer | Tests | Scope |
|-------|-------|-------|
| Unit | 17 | Password hashing, JWT issuance and verification, schema validation — in-process, no services required |
| Integration | 31 | Each service against its real datastore |
| API | 11 | Status-code semantics, versioning, error envelope, pagination bounds |
| End-to-end | 5 | Full order journey across five services, including saga compensation |
| Security | 21 | Token forgery, algorithm confusion, RBAC, object-level authorisation, GDPR erasure |

Run a single layer with `pytest -m unit` (or `integration`, `api`, `e2e`,
`security`).

### Coverage

```powershell
pytest -m unit --cov=services/user-service --cov-report=html
```

Coverage is measured only over modules exercised in-process by the unit
layer. Route handlers, session management and ORM models execute inside
containers where the coverage instrument has no visibility; those are
evidenced by the integration, API, end-to-end and security layers instead.

### Postman / Newman

32 requests, 70 assertions, organised into five folders that run in order.

```powershell
npm install -g newman newman-reporter-htmlextra
.\postman\run-newman.ps1
```

Folders depend on one another — Setup issues the tokens later folders
consume — so the collection must be run as a whole rather than as individual
requests.

---

## Performance testing

Locust scenarios covering load, stress, per-endpoint latency and horizontal
scaling.

```powershell
pip install -r perf/requirements-perf.txt
.\perf\run-tests.ps1      # four scenarios, ~15 minutes
.\perf\run-scaling.ps1    # 1 instance vs 3 instances, ~10 minutes
python perf\compare.py    # comparison table
```

See `perf/RUNNING-PERF.md` for scenario definitions and interpretation notes.

### Headline results

| Scenario | Users | Throughput | p50 | Error rate |
|----------|-------|-----------|-----|-----------|
| Baseline (health only) | 10 | 10 req/s | 13 ms | 0.00% |
| Load (mixed traffic) | 100 | 65 req/s | 33 ms | 0.02% |
| Stress (mixed traffic) | 500 | ~20 req/s | 290 ms | 1.86% |
| Scaling — 1 instance | 100 | 3.5 req/s | 690 ms | 35.22% |
| Scaling — 3 instances | 100 | 72.6 req/s | 130 ms | 0.00% |

Under stress, failures concentrated in PostgreSQL-backed endpoints
(`POST /orders` at 26.9%) while DynamoDB-backed catalogue reads degraded only
marginally (0.13%). CPU remained below 1% while thread counts rose fourfold,
indicating requests blocked awaiting database connections rather than starved
of compute. Scaling the Order Service horizontally tripled the aggregate
connection pool and eliminated failures entirely.

---

## AWS deployment

A representative slice was deployed to **eu-west-1 (Ireland)** and evidenced
under `evidence/09-aws/`:

| Service | Deployed as |
|---------|-------------|
| S3 | Static asset bucket, versioned and encrypted at rest |
| Secrets Manager | Database credentials, injected at task launch |
| DynamoDB | `smartretailx-products` with a `category-index` GSI |
| SNS + SQS | Event topic fanning out to a queue with a dead-letter queue |
| Lambda | Order event processor triggered by SQS |
| API Gateway | HTTP API fronting the Lambda function |
| ECR | Container registry for the catalogue service image |
| ECS Fargate | Catalogue service running as a 0.25 vCPU / 0.5 GB task |
| CloudWatch | Log aggregation, Logs Insights queries, CPU alarm with SNS action |

`infra/lambda/handler.py` contains the Lambda source.
`infra/nginx/nginx.conf` contains the load balancer configuration used to
demonstrate horizontal scaling locally.

Application code is portable between environments by a single environment
variable: `AWS_ENDPOINT_URL` points at LocalStack locally and is absent in
AWS, where boto3 resolves the regional endpoint.

All billable resources were torn down after evidence capture. Total
deployment cost was under one US dollar.

---

## Repository layout

```
smartretailx/
├── services/                    six microservices, one folder each
│   ├── user-service/            auth, RBAC, JWT issuance, GDPR erasure
│   ├── catalogue-service/       product catalogue on DynamoDB
│   ├── order-service/           saga orchestration, circuit breaker
│   ├── inventory-service/       conditional stock reservation
│   ├── payment-service/         PCI-DSS scope minimisation
│   └── notification-service/    WebSocket push + demo dashboard
├── shared/
│   ├── events.py                SNS/SQS publish, subscribe, DLQ wiring
│   └── logging_config.py        structured JSON logs with correlation IDs
├── api-specs/                   exported OpenAPI 3.1 specifications
├── tests/                       85 tests across five layers
├── postman/                     32-request collection, 70 assertions
├── perf/                        Locust scenarios and scaling comparison
├── infra/
│   ├── lambda/handler.py        AWS Lambda order event processor
│   └── nginx/nginx.conf         load balancer for horizontal scaling
├── scripts/export-specs.ps1     OpenAPI specification exporter
├── docs/decisions.md            engineering decision log
├── evidence/                    91 screenshots, organised by task
└── docker-compose.yml           ten-container local environment
```

---

## Design decisions

`docs/decisions.md` records sixteen decisions taken during development, each
with the problem encountered, the resolution, and the trade-off accepted.
Several document defects found and fixed:

- **D-012** — a GDPR erasure placeholder used an IANA special-use domain that
  failed response validation, causing `GET /api/v1/users` to return 500 once
  any account had been erased. Found by an automated security test.
- **D-015** — a fixed host port prevented horizontal scaling; resolved with an
  nginx load balancer using Docker's embedded DNS.
- **D-017** — the catalogue service always passed `endpoint_url` to boto3,
  defaulting to the LocalStack address, so the container failed to start in
  AWS. Found only by deploying: local emulation validated the SDK calls but
  not the configuration path used in production.

---

## Known limitations

Stated explicitly rather than left for a reader to discover:

- **Multi-region** is designed but not provisioned. Aurora Global Database,
  S3 cross-region replication and Route 53 failover appear in the
  architecture but were outside the available budget.
- **NAT Gateway** is shown in the target architecture; the deployed slice
  used public subnets with restrictive security groups, as a NAT Gateway
  would have consumed a large share of the available AWS credits.
- **CQRS** is discussed as a design option but not implemented.
- **Structured JSON logging** is implemented in the order, inventory, payment
  and notification services. The catalogue service was implemented earlier and
  retains the framework's default log format.
- **Coverage instrumentation** does not observe code running inside
  containers, so the reported figure understates effective test coverage.
- **Performance figures** were gathered with the load generator and the system
  under test sharing one machine, over loopback networking, with LocalStack
  emulating three AWS services in a single process. Absolute numbers
  understate real capacity; the relative comparisons remain valid.
- **SKU uniqueness** is not enforced in the catalogue. Idempotency is
  implemented where duplication causes harm — order creation and payment —
  and deliberately not where it does not.
- **WebSocket connections** are unauthenticated in the demonstration. A
  production deployment would validate a token during the handshake and scope
  each connection to that user's own events.

---

## Author

Shakya Matara · Cohort SENG23A1
BEng (Hons) Software Engineering, APIIT Sri Lanka / University of Staffordshire
