"""`presence-sidecar` — run the FastAPI sidecar (127.0.0.1 only, per-launch
random bearer token, printed to stdout for the shell app to consume)."""
from __future__ import annotations


def run(port: int = 8765) -> None:
    from .api import run_server
    run_server(port=port)


if __name__ == "__main__":
    import sys
    run(port=int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
