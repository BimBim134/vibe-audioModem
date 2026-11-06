# PyInstaller spec for the packaging spike (issue #3). Run from the repository root:
#   uv run pyinstaller packaging/vibemodem.spec --noconfirm
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

here = os.path.abspath(SPECPATH)  # noqa: F821 - provided by PyInstaller
root = os.path.dirname(here)

a = Analysis(  # noqa: F821
    [os.path.join(here, "entry.py")],
    pathex=[os.path.join(root, "src")],
    hiddenimports=collect_submodules("uvicorn"),
    # The page of the application is a folder of files (HTML, CSS, JS) next to its module.
    datas=[(os.path.join(root, "src", "vibemodem", "app", "assets"), "vibemodem/app/assets")],
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VibeModem",
    console=False,  # no terminal window for the operator
)
coll = COLLECT(exe, a.binaries, a.datas, name="VibeModem")  # noqa: F821

if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821
        coll,
        name="VibeModem.app",
        bundle_identifier="org.vibemodem.app",
        info_plist={
            "NSMicrophoneUsageDescription": "Vibe AudioModem listens to the audio input to receive messages.",
        },
    )
