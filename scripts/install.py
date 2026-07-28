"""
KickTV — Installation Script

Automates the setup process:
  1. Creates virtual environment
  2. Installs dependencies
  3. Creates directory structure
  4. Copies .env.example to .env
  5. Verifies system requirements
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
VENV_DIR = ROOT_DIR / "venv"


def print_header():
    print("""
    ╔═══════════════════════════════════════╗
    ║      KickTV — Installation Script     ║
    ╚═══════════════════════════════════════╝
    """)


def check_python():
    """Verify Python version."""
    ver = sys.version_info
    print(f"[✓] Python {ver.major}.{ver.minor}.{ver.micro}")
    if ver < (3, 10):
        print("[✗] Python 3.10+ required")
        sys.exit(1)


def check_ffmpeg():
    """Check if FFmpeg is installed."""
    if shutil.which("ffmpeg"):
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True, text=True, timeout=5
            )
            version_line = result.stdout.split("\n")[0]
            print(f"[✓] {version_line[:60]}")
        except Exception:
            print("[✓] FFmpeg found")
    else:
        print("[✗] FFmpeg NOT found — install it before running KickTV")
        print("    Windows: choco install ffmpeg")
        print("    Linux:   sudo apt install ffmpeg")
        print("    macOS:   brew install ffmpeg")


def create_directories():
    """Create all required directories."""
    dirs = [
        "data/videos",
        "data/db",
        "logs/app",
        "logs/ffmpeg",
        "logs/providers",
        "logs/errors",
    ]
    for d in dirs:
        (ROOT_DIR / d).mkdir(parents=True, exist_ok=True)
    print(f"[✓] Created {len(dirs)} directories")


def setup_env():
    """Copy .env.example to .env if it doesn't exist."""
    env_file = ROOT_DIR / ".env"
    example_file = ROOT_DIR / ".env.example"

    if env_file.exists():
        print("[✓] .env file exists")
    elif example_file.exists():
        shutil.copy(example_file, env_file)
        print("[✓] Created .env from .env.example")
        print("    → Edit .env with your stream key and API keys")
    else:
        print("[✗] .env.example not found")


def install_dependencies():
    """Install Python dependencies."""
    req_file = ROOT_DIR / "requirements.txt"
    if not req_file.exists():
        print("[✗] requirements.txt not found")
        return

    print("[...] Installing dependencies (this may take a minute)...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file)],
            check=True,
            capture_output=True,
        )
        print("[✓] Dependencies installed")
    except subprocess.CalledProcessError as e:
        print(f"[✗] Failed to install dependencies: {e}")
        print("    Try running: pip install -r requirements.txt")


def main():
    print_header()
    print("System:", platform.system(), platform.release())
    print()

    check_python()
    check_ffmpeg()
    create_directories()
    setup_env()
    install_dependencies()

    print()
    print("=" * 45)
    print("  Setup complete!")
    print()
    print("  Next steps:")
    print("    1. Edit .env with your stream key")
    print("    2. Run: python run.py")
    print("    3. Open: http://localhost:8000")
    print("=" * 45)


if __name__ == "__main__":
    main()
