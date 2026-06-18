#!/usr/bin/env python
import sys
import os
import socket

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run uvicorn
import uvicorn


def _is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock.connect_ex((host, port)) != 0


def _pick_port(host: str, candidates: list[int]) -> int:
    for port in candidates:
        if _is_port_available(host, port):
            return port
    return candidates[0]

if __name__ == "__main__":
    host = "127.0.0.1"
    port = _pick_port(host, [8000, 8010, 8020])
    print(f"[office-agent] Starting server at http://{host}:{port}")
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,
    )
