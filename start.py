#!/usr/bin/env python3
"""
start.py — GSM System Startup Script

Usage:
    python start.py              # auto-detect Docker, fall back to SQLite
    python start.py --sqlite     # force SQLite (skip Docker)
    python start.py --postgres   # force PostgreSQL via Docker
    python start.py --no-browser # don't open browser automatically
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import webbrowser

HOST = "127.0.0.1"
PORT = 8000
URL  = f"http://{HOST}:{PORT}"

POSTGRES_URL = "postgresql://postgres:password@localhost:5432/gsm"
SQLITE_URL   = "sqlite:///./gsm.db"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kwargs)


def docker_available() -> bool:
    try:
        result = run(["docker", "info"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def docker_compose_up() -> bool:
    print("[start] Starting Docker database (PostgreSQL)...")
    result = run(["docker-compose", "up", "-d"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[start] docker-compose failed:\n{result.stderr}")
        return False
    print("[start] Docker container started.")
    return True


def wait_for_postgres(timeout: int = 30) -> bool:
    print(f"[start] Waiting for PostgreSQL to be ready (up to {timeout}s)...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = run(
            ["docker", "exec", "gsm_postgres", "pg_isready", "-U", "postgres", "-d", "gsm"],
            capture_output=True,
        )
        if result.returncode == 0:
            print("[start] PostgreSQL is ready.")
            return True
        time.sleep(1)
    print("[start] Timed out waiting for PostgreSQL.")
    return False


def start_backend(database_url: str) -> subprocess.Popen:
    env = {**os.environ, "DATABASE_URL": database_url}
    print(f"[start] Starting FastAPI backend on {URL} ...")
    print(f"[start] DATABASE_URL = {database_url}")
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "backend.main:app",
            "--host", HOST, "--port", str(PORT), "--reload",
        ],
        env=env,
    )
    return proc


def wait_for_backend(timeout: int = 15) -> bool:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{URL}/health", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    parser = argparse.ArgumentParser(description="GSM startup script")
    parser.add_argument("--sqlite",     action="store_true", help="Force SQLite database")
    parser.add_argument("--postgres",   action="store_true", help="Force PostgreSQL via Docker")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser")
    args = parser.parse_args()

    # Determine database
    if args.sqlite:
        database_url = SQLITE_URL
        print("[start] Using SQLite (forced).")
    elif args.postgres:
        if not docker_available():
            print("[start] ERROR: Docker is not available. Cannot use --postgres.")
            sys.exit(1)
        if not docker_compose_up() or not wait_for_postgres():
            print("[start] ERROR: PostgreSQL failed to start.")
            sys.exit(1)
        database_url = POSTGRES_URL
    else:
        # Auto-detect
        if docker_available():
            print("[start] Docker detected — attempting PostgreSQL...")
            if docker_compose_up() and wait_for_postgres():
                database_url = POSTGRES_URL
            else:
                print("[start] Docker failed — falling back to SQLite.")
                database_url = SQLITE_URL
        else:
            print("[start] Docker not available — using SQLite.")
            database_url = SQLITE_URL

    # Start backend
    backend = start_backend(database_url)

    print(f"[start] Waiting for backend to come up...")
    if wait_for_backend():
        print(f"[start] Backend ready at {URL}")
        print(f"[start]   Demos page:        {URL}/demos")
        print(f"[start]   Staff tablet:      {URL}/staff")
        print(f"[start]   Management:        {URL}/management")
        print(f"[start]   API docs:          {URL}/docs")
        if not args.no_browser:
            webbrowser.open(f"{URL}/demos")
    else:
        print("[start] WARNING: Backend did not respond in time. Check logs above.")

    print("[start] Press Ctrl+C to stop.\n")
    try:
        backend.wait()
    except KeyboardInterrupt:
        print("\n[start] Shutting down backend...")
        backend.terminate()
        if database_url == POSTGRES_URL:
            print("[start] Stopping Docker containers...")
            run(["docker-compose", "down"])
        print("[start] Done.")


if __name__ == "__main__":
    main()
