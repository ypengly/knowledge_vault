"""Paths and user settings. API keys are NEVER stored in settings.json."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

APP_NAME = "KnowledgeVault"


def data_dir() -> Path:
    override = os.environ.get("KV_DATA_DIR")
    if override:
        p = Path(override)
    elif os.name == "nt":
        p = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    else:
        p = Path.home() / ".local" / "share" / APP_NAME
    (p / "files").mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class Settings:
    llm_provider: str = "none"          # none | ollama | openai_compat | anthropic
    llm_model: str = ""
    llm_base_url: str = ""              # blank = provider default
    embedder: str = "hashing"           # hashing | sentence_transformers
    st_model: str = "all-MiniLM-L6-v2"
    chunk_words: int = 180
    chunk_overlap: int = 30
    top_k: int = 6
    min_semantic_score: float = 0.45    # only used by true semantic embedders
    ocr_lang: str = "eng"
    tesseract_cmd: str = ""
    confirm_external: bool = True       # ask before every external AI request

    @classmethod
    def load(cls, directory: Path | None = None) -> "Settings":
        path = (directory or data_dir()) / "settings.json"
        s = cls()
        if path.exists():
            try:
                raw = json.loads(path.read_text("utf-8"))
                names = {f.name for f in fields(cls)}
                for k, v in raw.items():
                    if k in names:
                        setattr(s, k, v)
            except (OSError, ValueError):
                pass
        return s

    def save(self, directory: Path | None = None) -> None:
        path = (directory or data_dir()) / "settings.json"
        path.write_text(json.dumps(asdict(self), indent=2), "utf-8")
