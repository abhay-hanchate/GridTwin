"""Ask a Gemini model (through the local OmniRoute gateway) to read a paper and summarise it.

Key: read from C:\\Users\\524ta\\.omniroute\\gridtwin_key.txt (or env OMNIROUTE_API_KEY). Never print it.

  python research/omni_read.py models
  python research/omni_read.py ping
  python research/omni_read.py read <url-or-pdf-path> "<what GridTwin needs from this paper>"
"""
import io
import json
import os
import sys
from pathlib import Path

import requests

ENV_FILE = Path(__file__).with_name(".env")
if ENV_FILE.is_file():
    for line in ENV_FILE.read_text().splitlines():
        name, sep, value = line.partition("=")
        if sep and name.strip() and not line.lstrip().startswith("#") and value.strip():
            os.environ.setdefault(name.strip(), value.strip())

BASE = os.getenv("OMNIROUTE_BASE_URL", "http://localhost:20128").rstrip("/")
KEY_FILE = Path.home() / ".omniroute" / "gridtwin_key.txt"
MODEL = os.getenv("GRIDTWIN_READER_MODEL", "")
MAX_CHARS = 400_000

SYSTEM = (
    "You read research papers for an Indian low-voltage rooftop-solar grid digital twin (GridTwin). "
    "Reply in this exact structure, plain and short: "
    "1) What the paper does (2 lines). 2) Data used + whether public/Indian. 3) Method + key numbers/results. "
    "4) Code/repo link if stated. 5) Limits or red flags. 6) Verdict for GridTwin: useful / not useful and why. "
    "Quote numbers only if they appear in the text. If something is not in the text, say 'not stated'."
)


def key() -> str:
    k = os.getenv("OMNIROUTE_API_KEY") or (KEY_FILE.read_text().strip() if KEY_FILE.is_file() else "")
    if not k:
        sys.exit(f"No key: put it in research/.env as OMNIROUTE_API_KEY=...")
    return k


def call(path: str, payload: dict | None = None):
    h = {"Authorization": f"Bearer {key()}"}
    r = requests.post(BASE + path, json=payload, headers=h, timeout=300) if payload else requests.get(BASE + path, headers=h, timeout=60)
    if r.status_code >= 400:
        sys.exit(f"HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def load_text(src: str) -> str:
    if src.startswith("http"):
        r = requests.get(src, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data, is_pdf = r.content, r.content[:4] == b"%PDF"
    else:
        data = Path(src).read_bytes()
        is_pdf = data[:4] == b"%PDF"
    if is_pdf:
        import pypdf
        return "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(data)).pages)
    return data.decode("utf-8", "ignore")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "models":
        for m in call("/v1/models").get("data", []):
            print(m["id"])
    elif cmd == "ping":
        out = call("/v1/chat/completions", {"model": MODEL, "messages": [{"role": "user", "content": "Reply with the word OK."}]})
        print(out["choices"][0]["message"]["content"])
    elif cmd == "read" and len(sys.argv) >= 3:
        need = sys.argv[3] if len(sys.argv) > 3 else "general usefulness"
        text = load_text(sys.argv[2])[:MAX_CHARS]
        out = call("/v1/chat/completions", {"model": MODEL, "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"GridTwin needs: {need}\n\n--- PAPER TEXT ---\n{text}"}]})
        print(out["choices"][0]["message"]["content"])
    else:
        print(__doc__)


if __name__ == "__main__":
    if cmd := (sys.argv[1] if len(sys.argv) > 1 else ""):
        if cmd in ("ping", "read") and not MODEL:
            sys.exit("Set GRIDTWIN_READER_MODEL to an id from `models` first")
    main()
