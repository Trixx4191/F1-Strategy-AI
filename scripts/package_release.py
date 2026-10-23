"""Build an allowlisted release archive, excluding caches and local credentials.

First run `cd frontend && VITE_DEMO_MODE=true npm run build`.
"""
import hashlib
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "dist/f1-strategy-demo.tar.gz"

if __name__ == "__main__":
    for required in ("frontend/dist/index.html", "data/demo/bahrain-2024.json", "data/demo/default-run.json"):
        if not (ROOT / required).is_file():
            raise SystemExit(f"Missing release input: {required}")
    TARGET.parent.mkdir(exist_ok=True)
    entries = [ROOT / p for p in (
        "backend", "src", "frontend/dist", "data/demo", "requirements-runtime.txt",
        "Dockerfile.aws", "docker-compose.demo.yml", "deploy",
    )]
    with tarfile.open(TARGET, "w:gz") as archive:
        for entry in entries:
            files = sorted(entry.rglob("*")) if entry.is_dir() else [entry]
            for path in files:
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                    archive.add(path, arcname=path.relative_to(ROOT))
    digest = hashlib.sha256(TARGET.read_bytes()).hexdigest()
    TARGET.with_suffix(TARGET.suffix + ".sha256").write_text(f"{digest}  {TARGET.name}\n")
    print(f"{TARGET} ({TARGET.stat().st_size:,} bytes)\nSHA256 {digest}")
