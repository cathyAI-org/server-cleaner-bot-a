# Catcord Bots Framework

Shared framework for Matrix bots with individual bot services.

## Structure

```
./
  docker-compose.yml         # Bot orchestration
  framework/                 # Shared package
    catcord_bots/           # Python package (matrix, config, personality, state)
    Dockerfile              # Base image
  cleaner/                  # Cleaner bot
    main.py                 # Entry point
    cleaner.py              # Core logic
    Dockerfile
    config.yaml
  tests/                    # Test suite
```

## Features

- **Framework**: Shared Matrix client, config parsing, AI summary rendering, deduplication
- **Cleaner Bot**: Automated media cleanup with retention and pressure modes
- **Personality**: Optional summaries with personality via characters API
- **Deduplication**: Prevents duplicate notifications based on payload fingerprints

## Setup

Run `./setup.sh` and choose:
1. Docker (production)
2. Local Python (development)

## Build

```bash
docker build -t catcord-bots-framework:latest -f framework/Dockerfile framework
docker-compose build cleaner
```

## Run Cleaner Bot

Dry-run:
```bash
docker-compose run --rm cleaner --config /config/config.yaml --mode pressure --dry-run
docker-compose run --rm cleaner --config /config/config.yaml --mode retention --dry-run
```

Production:
```bash
docker-compose run --rm cleaner --config /config/config.yaml --mode pressure
docker-compose run --rm cleaner --config /config/config.yaml --mode retention
```

### CLI Flags

- `--mode {retention,pressure}` - Cleanup mode (required)
- `--dry-run` - Simulate without deleting
- `--debug` - Force send notification even if dedupe would skip
- `--force-notify` - Force send notification even on no-action

### Deduplication

The bot tracks payload fingerprints in `/state/{mode}_last.fp` to prevent duplicate notifications. Messages are only sent when:

- Payload changes (different deletions, disk usage, etc.)
- `--debug` flag is used (always send)
- `--force-notify` flag is used (always send)

Use `--force-notify` for scheduled daily summaries (e.g., 01:00 pressure check) and omit it for frequent checks (e.g., 2-minute pressure monitoring).

## AI Configuration

The personality renderer supports two API modes:

- `cathy_api_mode: "ollama"` - Uses Ollama `/api/chat` endpoint
- `cathy_api_mode: "openai"` - Uses OpenAI-compatible `/v1/chat/completions` endpoint

Set `cathy_api_model` to your model name (e.g., `llama3`, `gemma2:2b`, `cathy`).

### Characters API Authentication

To fetch private character prompts, configure:

- `characters_api_key` - API key for authentication
- `characters_api_key_header` - Header name (default: `X-API-Key`)

These are passed as HTTP headers when fetching from `/characters/{id}?view=private`.

Example config:
```yaml
add_personality:
  enabled: true
  characters_api_url: "http://192.168.1.59:8090"
  characters_api_key: "your_api_key_here"
  characters_api_key_header: "X-API-Key"
  character_id: "irina"
  cathy_api_url: "http://192.168.1.57:8100"
  cathy_api_mode: "ollama"
  cathy_api_model: "gemma2:2b"
```

## Tests

```bash
pytest tests/ -v
```