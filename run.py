"""
KickTV — Entry Point

Run the application with:
    python run.py

Or using uvicorn directly:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import shutil
import sys
from pathlib import Path

# Ensure project root is in path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))


def check_dependencies() -> bool:
    """Verify required system tools are available."""
    issues = []

    # Check FFmpeg
    if not shutil.which("ffmpeg"):
        issues.append(
            "FFmpeg not found. Install it:\n"
            "  Windows: choco install ffmpeg  OR  download from https://ffmpeg.org\n"
            "  Linux:   sudo apt install ffmpeg\n"
            "  macOS:   brew install ffmpeg"
        )

    # Check .env file
    env_file = ROOT_DIR / ".env"
    env_example = ROOT_DIR / ".env.example"
    if not env_file.exists():
        if env_example.exists():
            shutil.copy(env_example, env_file)
            print("[INFO] Created .env from .env.example — please edit it with your settings.")
        else:
            issues.append(".env file not found and no .env.example available.")

    if issues:
        print("\n⚠️  Pre-flight check issues:\n")
        for issue in issues:
            print(f"  • {issue}\n")
        return False

    return True


def main() -> None:
    """Start the KickTV application."""
    print("""
    =========================================
    |       KickTV - 24/7 Channel           |
    |   Automatic Streaming for Kick        |
    =========================================
    """)

    # Pre-flight checks
    if not check_dependencies():
        print("Fix the issues above and try again.")
        print("The server will still start, but some features may not work.\n")

    # Create required directories
    for d in ["data/videos", "data/db", "logs/app", "logs/ffmpeg", "logs/providers", "logs/errors"]:
        (ROOT_DIR / d).mkdir(parents=True, exist_ok=True)

    # Import settings after .env is ensured
    from app.config import settings

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
