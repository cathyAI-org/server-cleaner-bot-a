# Catcord Bots Framework

Shared framework for Matrix bots with individual bot services.

## Structure

```
./
  docker-compose.yml         # Bot orchestration
  framework/                 # Shared package
    catcord_bots/           # Python package
    Dockerfile              # Base image
  cleaner/                  # Cleaner bot
    main.py
    cleaner.py
    Dockerfile
    config.yaml
  tests/                    # Test suite
```

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

## Tests

```bash
pytest tests/ -v
```