# Knowledge Vault 🧠

A private, local-first desktop app that turns your documents into a searchable knowledge base and answers
questions **only from your own files — with exact citations**.

```
IMPORT → EXTRACT → CHUNK → INDEX → SEARCH → ASK → CITED ANSWERS
```

## Features

| Area | What you get |
|---|---|
| Import | PDF, DOCX, TXT, Markdown, CSV, images (OCR), web pages (URL). Drag-and-drop, multi-select, whole folders. Table shows filename, type, size, pages, import date, status. Duplicates are detected by SHA-256. |
| Collections | Work, School, Research, Business, Personal + your own. A document can be in several. |
| Search | Keyword (SQLite FTS5/BM25), semantic (vector index), or hybrid (rank fusion). Filters: collection, file type, import date. Matches are highlighted; click to open the exact page. |
| Ask | Chat over your knowledge base. Every answer lists `Source: <file> / Page N`; clicking opens the page with terms highlighted. |
| Notes | Markdown notes with folders, tags, search, live preview, and links to documents. |
| Dashboard | Documents, collections, notes, storage, recent searches and questions. |
| Privacy | Local by default. A banner always states whether processing is local or external. |

## Honesty guarantees

* **No fake answers.** If nothing relevant is retrieved, the app replies exactly:
  *"I couldn't find enough information in your knowledge base to answer this."* — and the LLM is **not even called**.
* **No AI configured?** You get the most relevant passages with citations, labelled as *not generated*.
* **LLM answers are checked.** Citation numbers must refer to retrieved passages; invalid ones are dropped. An answer
  with no valid citation is flagged "unverified" and the passages it saw are shown.
* **Semantic search, honestly described.** The default index is a fast, dependency-free *lexical* hashing model
  (stemmed words + word pairs). It matches related wording, not true synonyms. For real neural semantic search,
  `pip install sentence-transformers` and choose it in Settings (runs locally; downloads the model once).

## Privacy model

* Files are **copied** into the vault folder (`%APPDATA%\KnowledgeVault` on Windows); originals are never modified.
* Nothing is uploaded unless you (1) choose an external AI provider in Settings **and** (2) confirm each question in
  a dialog that lists which passages/files will be sent. Indexing, OCR and search never leave your machine.
* Adding a web page downloads that single URL after you confirm — nothing else touches the network.
* **API keys are never hard-coded or written to settings.json.** They come from the `KV_LLM_API_KEY` environment
  variable, the OS keyring (opt-in checkbox, needs `keyring`), or are held in memory for the session.
* Providers: *Ollama* and other servers on `localhost` are treated as **local**; anything else is **external**.

## Install & run (development)

Requires Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python -m knowledge_vault
```

### OCR (images and scanned PDFs)

1. Install the Tesseract engine: <https://github.com/UB-Mannheim/tesseract/wiki> (Windows installer).
2. Either add it to `PATH` or set **Settings → Tesseract path** (e.g. `C:\Program Files\Tesseract-OCR\tesseract.exe`).
3. Extra languages: tick them in the installer, then set **OCR language** (e.g. `eng+deu`).

Scanned PDF pages (almost no text layer) are OCR'd automatically; if Tesseract is missing the document still imports
and shows a warning.

### Using a local or external AI

*Local (recommended):* install [Ollama](https://ollama.com), `ollama pull <model>`, then Settings → provider
**Ollama**, model = that name.
*External:* choose **Anthropic API** or **OpenAI-compatible**, enter a model name and key. You are asked before every
request. Settings → *Test AI connection* sends only a "ping".

## Page citations

PDFs use real page numbers. Formats with no fixed pages get stable labels: DOCX/TXT/MD/web → `Section N`,
CSV → `Rows 41–80`, images → `Image`.

## Tests

```bash
python -m pytest -q          # or: python -m unittest discover -s tests -t .
```

Covers chunking, extraction (CSV, DOCX, PDF), the import pipeline, keyword/semantic/hybrid search and filters,
collections, notes, citation validation, the "not enough information" path, the external-consent guard, and a
headless Qt smoke test (auto-skipped without PySide6; PDF test skipped without PyMuPDF).

## Windows packaging

```bat
build_windows.bat
```

This creates a venv, installs dependencies, runs the tests, and builds `dist\KnowledgeVault\KnowledgeVault.exe`
with PyInstaller (`knowledge_vault.spec`). Distribute the whole `dist\KnowledgeVault` folder (zip it), or compile
`installer.iss` with [Inno Setup](https://jrsoftware.org/isinfo.php) for a one-file installer.

Notes:
* Tesseract is a separate install on the target PC (or bundle its folder and point Settings at it).
* If the exe fails to start, set `console=True` in the spec and rebuild to see the error.
* Including `sentence-transformers` makes the build very large; the default build does not need it.

## Project layout

```
knowledge_vault/
  core.py       Vault facade (db + embedder + index)    qa.py        grounded Q&A, citations
  db.py         SQLite schema, FTS5, notes, history     llm.py       optional providers (stdlib HTTP)
  extract.py    PDF/DOCX/TXT/MD/CSV/image/URL           search.py    keyword / semantic / hybrid + filters
  chunker.py    page-bounded chunking                   ingest.py    import pipeline
  embeddings.py hashing + neural embedders, FAISS/NumPy index      keystore.py  API-key handling
  ui/           PySide6 pages, viewer, background workers
tests/
```

## Known limitations

* Notes are searchable in the Notes page but are not (yet) part of the Q&A index.
* DOCX has no reliable page numbers, so sections are cited instead.
* The first import with the neural embedder downloads the model.
* The Qt UI was written without access to a display in the authoring environment; the core engine is fully
  unit-tested and the UI has a headless smoke test — please report any platform-specific UI glitches.
