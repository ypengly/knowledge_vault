# PyInstaller spec -  build with:  pyinstaller knowledge_vault.spec --noconfirm
from PyInstaller.utils.hooks import collect_submodules

hidden = collect_submodules("knowledge_vault")
for optional in ("faiss", "keyring", "sentence_transformers"):
    try:
        hidden += collect_submodules(optional)
    except Exception:
        pass

a = Analysis(
    ["run_app.py"],
    pathex=["."],
    hiddenimports=hidden,
    excludes=["tkinter", "matplotlib"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="KnowledgeVault",
    console=False,          # set True while debugging
    # icon="assets/icon.ico",
)
coll = COLLECT(exe, a.binaries, a.datas, name="KnowledgeVault")
