"""
LessonForge backend package.

Loads `.env` from the repo root at package import time so secrets
(ANTHROPIC_API_KEY today, anything else later) are available to any
process that imports something from `app` — regardless of whether the
shell that launched the process happened to inherit the right env vars.

`load_dotenv` does not override env vars that are already set, so a
real env var still wins over the `.env` file. The `.env` is a fallback
for shells that didn't inherit the persistent OS-level value.
"""

from pathlib import Path

from dotenv import load_dotenv

# .env lives at the repo root (one directory up from app/).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
