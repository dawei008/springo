# Springo FastAPI

Springo - AI Assistant Backend powered by Amazon Bedrock, rebuilt with FastAPI.

## Overview

This is the FastAPI version of Springo, migrated from Flask to leverage async/await for better performance and scalability.

### Key Features

- **Async/Await**: Full async support for non-blocking I/O
- **Pydantic Models**: Type-safe request/response validation
- **Auto-generated Docs**: OpenAPI/Swagger documentation at `/docs`
- **MCP Tools Integration**: Async tool execution with parallel support
- **SSE Streaming**: Server-Sent Events for real-time responses
- **Session Management**: JSONL-based session persistence

## Quick Start

### Prerequisites

- Python 3.11+
- AWS credentials configured
- Amazon Bedrock access

### Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Server

```bash
# Development mode (with auto-reload)
uvicorn api.main:app --host 0.0.0.0 --port 8081 --reload

# Production mode
uvicorn api.main:app --host 0.0.0.0 --port 8081 --workers 4
```

### Using the Convenience Script

```bash
# Start server
python run.py

# Or with custom options
python run.py --port 8082 --workers 2
```

## API Endpoints

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/docs` | Swagger UI documentation |
| GET | `/openapi.json` | OpenAPI schema |

### Messages API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/messages` | Send message to Claude (supports streaming) |
| POST | `/v1/messages-auto` | Auto tool loop mode |

### Tools API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/tools/list` | List available tools |
| POST | `/v1/tools/execute` | Execute single tool |
| POST | `/v1/tools/batch` | Execute multiple tools |
| GET | `/v1/tools/{name}` | Get tool info |

### Sessions API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/sessions` | List sessions |
| GET | `/v1/sessions/{id}` | Get session |
| POST | `/v1/sessions/{id}` | Save session |
| DELETE | `/v1/sessions/{id}` | Delete session |
| POST | `/v1/sessions/hash` | Generate session hash |

### Context API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/context` | Get context |
| POST | `/v1/context/add` | Add context |
| DELETE | `/v1/context` | Clear context |

### News API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/news/search` | Search news |
| GET | `/v1/news/search` | Search news (GET) |

### Images API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/images/generate` | Generate image |
| POST | `/v1/images/search` | Search images |
| POST | `/v1/images/upload` | Upload image |

## Project Structure

```
springo-fastapi/
├── api/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── config.py            # Pydantic settings
│   ├── dependencies.py      # Dependency injection
│   ├── routers/
│   │   ├── messages.py      # Messages endpoints
│   │   ├── tools.py         # Tools endpoints
│   │   ├── sessions.py      # Sessions endpoints
│   │   ├── context.py       # Context endpoints
│   │   ├── news.py          # News endpoints
│   │   ├── images.py        # Images endpoints
│   │   └── health.py        # Health endpoints
│   ├── services/
│   │   ├── bedrock.py       # Bedrock async client
│   │   ├── tool_manager.py   # Tool manager
│   │   └── session_store.py # Session persistence
│   ├── models/
│   │   ├── requests.py      # Request models
│   │   └── responses.py     # Response models
│   └── utils/
│       └── streaming.py     # SSE utilities
├── tests/
│   └── e2e/                 # E2E tests
├── requirements.txt
├── pytest.ini
├── run.py                   # Convenience runner
└── README.md
```

## Configuration

Environment variables (prefix: `SPRINGO_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SPRINGO_AWS_REGION` | `us-west-2` | AWS region |
| `SPRINGO_BEDROCK_MODEL_ID` | `anthropic.claude-sonnet-4-20250514-v1:0` | Bedrock model |
| `SPRINGO_HOST` | `0.0.0.0` | Server host |
| `SPRINGO_PORT` | `8081` | Server port |
| `SPRINGO_DEBUG` | `true` | Debug mode |

## Testing

```bash
# Run all E2E tests
pytest tests/e2e/ -v

# Run with coverage
pytest tests/e2e/ -v --cov=api --cov-report=html

# Run benchmarks
pytest tests/e2e/test_benchmark.py -v -s
```

## Performance

Benchmark results (M3 Mac):

| Endpoint | Requests/sec |
|----------|--------------|
| `/health` | ~1,000+ |
| `/v1/tools/list` | ~450 |
| `/v1/tools/execute` | ~170 |
| `/v1/sessions` | ~28 |
| Health latency | ~1.2ms |

## Migration from Flask

This project is a FastAPI rewrite of the original Flask-based Springo. Key improvements:

1. **Async/Await**: Non-blocking I/O throughout
2. **Type Safety**: Pydantic models for all request/response
3. **Auto Documentation**: OpenAPI/Swagger auto-generated
4. **Parallel Tools**: Concurrent tool execution support
5. **Better Testing**: Comprehensive E2E test suite

## License

Licensed under the [Apache License 2.0](LICENSE).
