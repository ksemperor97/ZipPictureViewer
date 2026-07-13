# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from scripts.check_release_version import read_project_version


PROJECT_ROOT = Path(SPECPATH).resolve()
APP_VERSION = read_project_version(PROJECT_ROOT)
TARGET_MACOS_VERSION = os.environ.get('MACOSX_DEPLOYMENT_TARGET', '13.0')

a = Analysis(
    ['zippictureviewer_launcher.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['AppKit'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6.Qt3DAnimation',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DExtras',
        'PySide6.Qt3DInput',
        'PySide6.Qt3DLogic',
        'PySide6.Qt3DRender',
        'PySide6.QtCharts',
        'PySide6.QtConcurrent',
        'PySide6.QtDataVisualization',
        'PySide6.QtGraphs',
        'PySide6.QtHttpServer',
        'PySide6.QtMultimedia',
        'PySide6.QtNetwork',
        'PySide6.QtOpenGL',
        'PySide6.QtPdf',
        'PySide6.QtPdfWidgets',
        'PySide6.QtPositioning',
        'PySide6.QtPrintSupport',
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuick3D',
        'PySide6.QtQuickControls2',
        'PySide6.QtQuickWidgets',
        'PySide6.QtRemoteObjects',
        'PySide6.QtScxml',
        'PySide6.QtSensors',
        'PySide6.QtSerialBus',
        'PySide6.QtSerialPort',
        'PySide6.QtSql',
        'PySide6.QtStateMachine',
        'PySide6.QtSvg',
        'PySide6.QtSvgWidgets',
        'PySide6.QtTest',
        'PySide6.QtTextToSpeech',
        'PySide6.QtWebChannel',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebSockets',
        'PySide6.QtXml',
        'PySide6.QtXmlPatterns',
    ],
    noarchive=False,
    optimize=0,
)
a.binaries = [
    item
    for item in a.binaries
    if not (
        'Qt/translations' in item[0]
        or 'Qt/plugins/tls' in item[0]
        or 'Qt/plugins/bearer' in item[0]
        or 'Qt/plugins/networkinformation' in item[0]
        or 'Qt/plugins/sqldrivers' in item[0]
        or 'Qt/plugins/qmltooling' in item[0]
        or 'Qt/plugins/printsupport' in item[0]
    )
]
a.datas = [
    item
    for item in a.datas
    if 'Qt/translations' not in item[0]
]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ZipPictureViewer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ZipPictureViewer',
)
app = BUNDLE(
    coll,
    name='ZipPictureViewer.app',
    icon='assets/ZipPictureViewer.icns',
    bundle_identifier='com.ksemperor97.ZipPictureViewer',
    info_plist={
        'CFBundleDisplayName': 'ZipPictureViewer',
        'CFBundleShortVersionString': APP_VERSION,
        'CFBundleVersion': APP_VERSION,
        'LSMinimumSystemVersion': TARGET_MACOS_VERSION,
        'NSHighResolutionCapable': True,
    },
)
