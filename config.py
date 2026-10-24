"""Portable local-development configuration."""
from pathlib import Path
import os
import sys

BASE_DIR = Path(__file__).resolve().parent
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else BASE_DIR

class Config:
    HOST = "127.0.0.1"
    PORT = 5000
    DEBUG = False
    MAX_CONTENT_LENGTH = 16 * 1024
    DATA_DIR = Path(os.environ.get("REVIVEOS_DATA_DIR", str(APP_DIR / "data")))
    OLLAMA_URL = "http://127.0.0.1:11434"
