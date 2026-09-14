"""CLI: python -m veritas.api [--host 127.0.0.1] [--port 8000]"""

import argparse

import uvicorn

from veritas.api.app import create_app
from veritas.config import ApiSettings

parser = argparse.ArgumentParser(description="Serve the read-only API and the graph explorer page.")
parser.add_argument("--host", default="127.0.0.1", help="localhost by default; the API has no authentication")
parser.add_argument("--port", type=int, default=8000)
args = parser.parse_args()

settings = ApiSettings()
print(f"graph {settings.graph_path}, audit log {settings.audit_path}, anchor {settings.anchor_path}")
uvicorn.run(create_app(settings), host=args.host, port=args.port)
