import os
import sys

# Never let tests read the real .env (real Telegram token, real secrets).
os.environ["AANGAN_NO_DOTENV"] = "1"
for _k in [k for k in os.environ if k.startswith(("TELEGRAM_", "SMTP_", "VAANI_", "GOOGLE_", "TOOL_SECRET"))]:
    del os.environ[_k]
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tests"))
SEED = ROOT / "seed" / "Case 03 Seed Data"
