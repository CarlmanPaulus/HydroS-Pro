# -*- mode: python ; coding: utf-8 -*-
import os
import glob
import shutil

a = Analysis(
    ['run_app.py'],
    pathex=[],
    binaries=[],
    datas=[('manual_extractor\\HydroS.ico', '.'), ('manual_extractor\\app.qss', '.'), ('RAW_combiner\\app.qss', 'RAW_combiner')],
    hiddenimports=['secrets'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'scipy', 'matplotlib', 'tkinter', 'IPython', 'PIL', 'Pillow',
        'cryptography', 'cffi', '_cffi_backend',
        'unittest', 'xmlrpc', 'pydoc_data', 'doctest',
        'lib2to3', 'test', 'distutils', 'setuptools',
    ],
    noarchive=False,
    optimize=0,
)

# ── Strip unused Qt modules from binaries & datas ──────────────
UNUSED_QT = [
    'Qt6Quick', 'Qt6Qml', 'Qt6QmlModels', 'Qt6QmlWorkerScript',
    'Qt6Pdf', 'Qt6OpenGL', 'Qt6VirtualKeyboard', 'Qt6Designer',
    'Qt6Help', 'Qt6Multimedia', 'Qt6Positioning', 'Qt6Location',
    'Qt6Bluetooth', 'Qt6Nfc', 'Qt6RemoteObjects', 'Qt6Sensors',
    'Qt6SerialPort', 'Qt6Test', 'Qt6WebChannel', 'Qt6WebSockets',
    'Qt6Xml', 'Qt63DCore', 'Qt63DRender', 'Qt63DInput',
    'Qt6ShaderTools', 'Qt6SpatialAudio',
]

def _is_unwanted(name):
    low = name.lower()
    for mod in UNUSED_QT:
        if mod.lower() in low:
            return True
    # Strip Qt translations (6.5 MB)
    if 'translations' in low and 'qt' in low:
        return True
    return False

a.binaries = [b for b in a.binaries if not _is_unwanted(b[0])]
a.datas = [d for d in a.datas if not _is_unwanted(d[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HydroS_Pro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='manual_extractor\\HydroS.ico',
)

icon_beside_exe = [('manual_extractor\\HydroS.ico', 'HydroS.ico', 'DATA')]

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    icon_beside_exe,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='HydroS_Pro',
)
