# ByteBattles

ByteBattles is a competitive programming platform built around a FastAPI backend and a Redis-driven asynchronous judge which can auto-scale. It supports problem management, testcase ingestion, submission workflows, and isolated execution of user code inside pre-warmed Docker sandboxes.

The system is designed to be practical, fast, and scalable on a single machine while remaining ready for horizontal expansion later.

### Checkout judge/Judge_Architecture.pdf

## Highlights

- FastAPI backend for authentication, users, problems, and submissions
- Redis-backed asynchronous judging pipeline
- Multi-process and multi-threaded judge orchestration
- Spawns/Destroys new judge worker automatically depending on the load
- Heartbeat checking for judge worker and retrying stuck or failed submissions
- Pre-warmed Docker sandbox pools for low-latency execution
- PostgreSQL for persistent metadata
- MinIO object storage for testcase and submission artifacts
- Isolated execution for C, C++, Python, and Java
- Automated verdict generation with CPU and memory limits
- Sandbox Manager to manage the pre-warmed container pool (multi threaded)

## Architecture

ByteBattles follows a queue-centric architecture:

```text
Client
  ↓
FastAPI API
  ↓
PostgreSQL + MinIO
  ↓
Redis submission queue
  ↓
Judge workers
  ↓
Warm sandbox pool
  ↓
Docker isolated execution
  ↓
Verdict update
```

### Core services

#### API service
The API handles:
- user registration and login
- JWT / OAuth2-based authentication
- problem creation and listing
- testcase upload
- submission creation and retrieval

#### Judge system
The judge system handles:
- submission consumption from Redis
- sandbox leasing from warm pools
- sending signal to maintain warm pool
- compilation and execution
- testcase comparison
- verdict generation
- sandbox cleanup

#### Storage layer
- PostgreSQL stores users, problems, submissions, and metadata
- MinIO stores testcase files and submitted source code

## Features

### Authentication
- Register and login endpoints
- Token-based authentication
- Protected routes for user, problem, and submission management

### Problem management
- Create problems with title, description, difficulty, tags, constraints, and sample I/O
- Upload testcase bundles
- Retrieve problems and problem details
- Track accepted submission counts

### Submission workflow
- Submit code against a problem
- Store code in object storage
- Enqueue submission ID for asynchronous judging
- Fetch verdict once judged

### Judge execution
- Managed by Judge Orchestrator
- Spawns/Kills Judge Workers automatically depending on current load
- Supports C, C++, Python, and Java
- Uses prebuilt language-specific Docker images
- Enforces execution limits
- Compares program output against testcase output
- Produces verdicts - AC, WA, TLE, MLE, CE, RE

### Sandbox pooling
- Maintained by Sandbox Manager
- Used multiple Creator Workers (multithreaded) to create containers
- Warm container pool maintained ahead of time
- Reduced container startup overhead
- Respawn lifecycle handled separately by pubsub
- Better throughput under high load

## Repository layout

```text
ByteBattles/
├── README.md
├── api
│   ├── app
│   │   ├── core
│   │   │   ├── database.py
│   │   │   ├── __init__.py
│   │   │   └── storage.py
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── models
│   │   │   ├── enums.py
│   │   │   ├── __init__.py
│   │   │   ├── problem.py
│   │   │   ├── submission.py
│   │   │   └── user.py
│   │   ├── routes
│   │   │   ├── auth.py
│   │   │   ├── __init__.py
│   │   │   ├── problems.py
│   │   │   ├── submissions.py
│   │   │   └── users.py
│   │   ├── schemas
│   │   │   ├── __init__.py
│   │   │   ├── problems.py
│   │   │   ├── submissions.py
│   │   │   └── user.py
│   │   └── utils
│   │       ├── __init__.py
│   │       ├── oauth2.py
│   │       ├── password_manager.py
│   │       └── redis_utils.py
│   └── __init__.py
├── config.py
└── judge
    ├── Architecture.pdf
    ├── images
    │   ├── build_command.sh
    │   ├── gcc
    │   │   └── Dockerfile
    │   ├── java
    │   │   └── Dockerfile
    │   └── python
    │       └── Dockerfile
    ├── __init__.py
    ├── judge_worker
    │   ├── database.py
    │   ├── executor.py
    │   ├── __init__.py
    │   ├── pipeline.py
    │   ├── redis_queue.py
    │   ├── storage_adapter.py
    │   ├── types.py
    │   └── worker.py
    ├── models.py
    ├── run.py
    ├── sandbox_manager
    │   ├── __init__.py
    │   └── main.py
    └── utils.py
```

## API overview

### Authentication
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`

### Users
- `GET /users/me`
- `PATCH /users/me`
- `DELETE /users/me`
- `GET /users/{username}`

### Problems
- `GET /problems/`
- `POST /problems/`
- `GET /problems/{problem_id}`
- `POST /problems/tag`
- `DELETE /problems/`

### Submissions
- `POST /submissions/`
- `GET /submissions/`
- `GET /submissions/{submission_id}`

## Verdicts

ByteBattles supports the following verdicts:

- `AC` — Accepted
- `WA` — Wrong Answer
- `TLE` — Time Limit Exceeded
- `MLE` — Memory Limit Exceeded
- `CE` — Compilation Error
- `RE` — Runtime Error
- `PD` — Pending

## How judge components work

### How Judge Orchestrator Works
1. Spawns one instance of sandbox manager
2. Loops infinitely with 2 second sleep
3. Does health check of each worker in every iteration and kills the dead one
4. Calculates expected workers depending on the load
5. Creates / Destroys judge workers depending on the expected count
6. Manages state of each judge worker in redis
7. Responsible for startup and shutdown of whole judge system

### How Judge Worker Works

1. Pops submission ID from judge queue
2. Fetches the corresponding submission object and runtime constraints from PostgreSQL
3. Fetches testcases' metadata from PostgreSQL
4. Pops a created container from container queue
5. Sends a signal to sandbox manager to replenish container supply (uses PubSub)
5. Fetches source code from MinIO
6. Copies source code into the container and compiles it
7. For each testcase, Fetched the content from MinIO and then executes it on the compiled code
8. Calculates the Verdict
9. Updates the result in PostgreSQL

### How Sandbox Manager Works

1. Spawns fixed number of creator workers for container creation
2. Initializes the pool by creating some initial amount of containers
3. Listens for Publish signals from judge workers
4. Queues creation task for creator workers
5. A creator worker picks up the task and pushes container ID to redis queue after creating container

## Why this architecture

This design was chosen to keep judging asynchronous and fast.

### Benefits
- low latency due to warm sandbox pools
- better throughput under burst load
- simple horizontal scaling with more workers
- clean separation between API, storage, and execution
- safer execution through Docker isolation

## Performance notes

The judge was benchmarked under high load and was able to saturate all available CPU cores on the host machine. This confirmed that the architecture is CPU-bound rather than queue-bound or storage-bound in the tested setup.

## Technologies used

- FastAPI
- PostgreSQL
- Redis
- MinIO
- Docker
- SQLAlchemy
- Python
- Multiprogramming

## Setup

### Prerequisites
- Python 3.12+
- Docker
- Redis
- PostgreSQL
- MinIO
- All packages in `requirements.txt`

### Run the API
```bash
uvicorn api.app.main:app
```

### Run the judge
```bash
python -m judge.run
```

## Configuration

The project uses fixed constants in early development. Later, environment variables can be introduced for deployment flexibility.

Important settings include:
- Redis host, port, and DB
- PostgreSQL database URL
- MinIO bucket names
- Judge queue names
- Sandbox memory and PID limits
- Language-specific Docker images

## Sandbox images

The judge uses language-specific Docker images:

- `judge-gcc` for C and C++
- `judge-python` for Python
- `judge-java` for Java

These images are kept minimal to reduce startup overhead and improve sandbox pool efficiency.

## Security model

The judge containers are isolated using:
- dropped Linux capabilities
- network disabled
- no-new-privileges
- memory and PID limits
- read-only filesystem where possible

This reduces the attack surface of executing untrusted user code.

## Future improvements

Planned upgrades may include:
- Redis Streams for stronger job recovery semantics
- distributed judge nodes
- better worker heartbeats and retries
- improved memory measurement
- more advanced output checking
- container runtime alternatives such as nsjail or minijail

## Project goals

ByteBattles is intended to be more than a CRUD application. It is a systems-heavy project focused on:
- distributed execution
- sandboxing
- queue-based orchestration
- low-latency worker design
- scalable backend architecture

## License

Copyright - 2026 - DIPANSHU TIWARI

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

---

Built for learning, systems engineering, and competitive programming infrastructure.
