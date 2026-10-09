import os
import tempfile
from pathlib import Path

from knowledge_vault.config import Settings
from knowledge_vault.core import Vault


def make_vault(**kw) -> tuple[Vault, Path]:
    tmp = Path(tempfile.mkdtemp(prefix="kv_test_"))
    return Vault(tmp, Settings(**kw)), tmp


def write(tmp: Path, name: str, text: str) -> Path:
    p = tmp / name
    p.write_text(text, "utf-8")
    return p
