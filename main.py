import argparse
import os
import sys
import yaml

def load_config(path: str) -> dict:
    """Load YAML configuration file.
    
    :param path: Path to config file
    :return: Configuration dictionary
    """
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def main():
    """Entry point for bot-a."""
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--mode", choices=["retention", "pressure"], required=True)
    args = p.parse_args()

    cfg = load_config(args.config)
    os.makedirs("/state", exist_ok=True)

    mxid = (cfg.get("bot") or {}).get("mxid")
    hs = cfg.get("homeserver_url")
    print(f"bot-a ok: mode={args.mode}, homeserver_url={hs}, mxid={mxid}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"bot-a fatal: {e}", file=sys.stderr)
        raise
