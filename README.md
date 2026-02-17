# server-cleaner-bot-a

Matrix bot for server cleanup operations.

## Usage

```bash
python main.py --mode retention --config config.yaml
python main.py --mode pressure --config config.yaml
```

## Modes

- `retention`: Cleanup based on retention policies
- `pressure`: Cleanup based on storage pressure

## Configuration

See `config.yaml` for bot settings including homeserver URL and credentials.
