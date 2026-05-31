#!/usr/bin/env python3
"""Notebook kod hücrelerini sırayla çalıştırır (nbconvert kernel çökmesine karşı)."""
from __future__ import annotations

import json
import os
import sys
import traceback
from io import StringIO
from pathlib import Path

# Proje kökü
ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "bitirme_projesi_jpynb.ipynb"
os.chdir(ROOT / "notebooks")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))

os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib

matplotlib.use("Agg")

def _strip_magics(src: str) -> str:
    lines = []
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("%pip") or s.startswith("!pip"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _save(nb: dict) -> None:
    NOTEBOOK.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    start_cell = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    globs = {"__name__": "__main__"}
    if start_cell > 0:
        print(
            f"Uyarı: hücre {start_cell}+ için önce 0–{start_cell - 1} çalıştırılmalı; "
            "durum kaydı yok, tam çalıştırma yapılıyor.",
            flush=True,
        )
        start_cell = 0
    failed = None

    for i, cell in enumerate(nb["cells"]):
        if i < start_cell:
            continue
        if cell["cell_type"] != "code":
            continue
        src = _strip_magics("".join(cell["source"]))
        if not src.strip():
            continue
        print(f"\n{'='*60}\nCell {i}\n{'='*60}", flush=True)
        out = StringIO()
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = out
        try:
            exec(compile(src, f"<cell {i}>", "exec"), globs)
            cell["execution_count"] = i + 1
            cell["outputs"] = [
                {
                    "output_type": "stream",
                    "name": "stdout",
                    "text": out.getvalue().splitlines(keepends=True) or ["\n"],
                }
            ]
            _save(nb)
        except Exception as exc:
            sys.stdout, sys.stderr = old_stdout, old_stderr
            print(out.getvalue(), end="")
            print(f"❌ Cell {i} failed: {exc}", file=sys.stderr)
            traceback.print_exc()
            cell["outputs"] = [
                {
                    "output_type": "stream",
                    "name": "stdout",
                    "text": out.getvalue().splitlines(keepends=True),
                },
                {
                    "output_type": "error",
                    "ename": type(exc).__name__,
                    "evalue": str(exc),
                    "traceback": traceback.format_exc().splitlines(keepends=True),
                },
            ]
            _save(nb)
            failed = i
            break
        finally:
            if failed is None:
                sys.stdout, sys.stderr = old_stdout, old_stderr
                text = out.getvalue()
                if text:
                    print(text, end="")

    _save(nb)
    if failed is not None:
        print(f"\nDurduruldu: hücre {failed}", file=sys.stderr)
        return 1
    print("\n✅ Tüm kod hücreleri tamamlandı; çıktılar notebook'a yazıldı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
