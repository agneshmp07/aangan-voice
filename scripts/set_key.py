"""Put a key from the clipboard into .env and data/vercel.env, then copy data/vercel.env to the clipboard.

Usage (copy the key first):   python scripts/set_key.py VAANI_API_KEY
Then paste into Vercel -> Settings -> Environment Variables -> vercel_env, Save, Redeploy.
The key is never printed.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {"VAANI_API_KEY", "HUBSPOT_TOKEN", "GOOGLE_CALENDAR_ID", "GOOGLE_SERVICE_ACCOUNT_JSON"}


def clipboard() -> str:
    out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], capture_output=True, text=True)
    return out.stdout.strip()


def set_line(path: Path, name: str, value: str) -> None:
    text = path.read_text(encoding="utf8") if path.exists() else ""
    line = f"{name}={value}"
    if re.search(rf"^{name}=.*$", text, flags=re.M):
        text = re.sub(rf"^{name}=.*$", lambda _: line, text, flags=re.M)
    else:
        text = text.rstrip("\n") + "\n" + line + "\n"
    path.write_text(text, encoding="utf8")


def main() -> None:
    name = (sys.argv[1] if len(sys.argv) > 1 else "").upper()
    if name not in ALLOWED:
        sys.exit(f"Name must be one of: {', '.join(sorted(ALLOWED))}")
    value = clipboard()
    if name == "GOOGLE_SERVICE_ACCOUNT_JSON":
        value = " ".join(value.split())  # one line, so it fits a .env line
        if '"private_key"' not in value:
            sys.exit("Clipboard doesn't look like a service-account JSON file. Copy the whole file and retry.")
    elif not value or " " in value or len(value) < 8:
        sys.exit("Clipboard doesn't look like a key. Copy the key and retry.")
    for p in (ROOT / ".env", ROOT / "data" / "vercel.env"):
        set_line(p, name, value)
    blob = (ROOT / "data" / "vercel.env").read_text(encoding="utf8")
    subprocess.run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"], input=blob, text=True)
    print(f"{name} saved ({len(value)} chars) to .env and data/vercel.env.")
    print("data/vercel.env is now on your clipboard -> paste it into Vercel 'vercel_env', Save, then Redeploy.")


if __name__ == "__main__":
    main()
