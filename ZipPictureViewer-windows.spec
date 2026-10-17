# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VSVersionInfo,
    VarFileInfo,
    VarStruct,
)
from scripts.check_release_version import read_project_version, windows_version_tuple


PROJECT_ROOT = Path(SPECPATH).resolve()
APP_VERSION = read_project_version(PROJECT_ROOT)
WINDOWS_VERSION = windows_version_tuple(APP_VERSION)

# Editable installs expose a source-tree egg-info before their installed dist-info.
# Bundle the installed metadata so importlib.metadata observes wheel-style metadata.
ORIGINAL_SYS_PATH = sys.path.copy()
try:
    sys.path[:] = [
        entry
        for entry in sys.path
        if entry and Path(entry).resolve() != PROJECT_ROOT
    ]
    DISTRIBUTION_METADATA = copy_metadata('zip-picture-viewer')
finally:
    sys.path[:] = ORIGINAL_SYS_PATH

RELEASE_METADATA_DIR = PROJECT_ROOT / 'build' / 'release-metadata'
RELEASE_METADATA_DATAS = [
    (str(RELEASE_METADATA_DIR / 'build-provenance.json'), 'release'),
    (str(RELEASE_METADATA_DIR / 'dependency-manifest.txt'), 'release'),
]
VERSION_INFO = VSVersionInfo(
    ffi=FixedFileInfo(filevers=WINDOWS_VERSION, prodvers=WINDOWS_VERSION),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    '040904B0',
                    [
                        StringStruct('CompanyName', 'ksemperor97'),
                        StringStruct('FileDescription', 'Zip Picture Viewer'),
                        StringStruct('FileVersion', APP_VERSION),
                        StringStruct('InternalName', 'ZipPictureViewer'),
                        StringStruct('OriginalFilename', 'ZipPictureViewer.exe'),
                        StringStruct('ProductName', 'Zip Picture Viewer'),
                        StringStruct('ProductVersion', APP_VERSION),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct('Translation', [1033, 1200])]),
    ],
)

a = Analysis(
    ['zippictureviewer_launcher.py'],
    pathex=[],
    binaries=[],
    datas=[*DISTRIBUTION_METADATA, *RELEASE_METADATA_DATAS],
    hiddenimports=[],
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
        'pyobjc',
    ],
    noarchive=False,
    optimize=0,
)
a.binaries = [
    item
    for item in a.binaries
    if not (
        'PySide6/translations' in item[0].replace('\\', '/')
        or 'PySide6/plugins/tls' in item[0].replace('\\', '/')
        or 'PySide6/plugins/bearer' in item[0].replace('\\', '/')
        or 'PySide6/plugins/networkinformation' in item[0].replace('\\', '/')
        or 'PySide6/plugins/sqldrivers' in item[0].replace('\\', '/')
        or 'PySide6/plugins/qmltooling' in item[0].replace('\\', '/')
        or 'PySide6/plugins/printsupport' in item[0].replace('\\', '/')
    )
]
a.datas = [
    item
    for item in a.datas
    if 'Qt/translations' not in item[0].replace('\\', '/')
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
    icon='assets/ZipPictureViewer.ico',
    version=VERSION_INFO,
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
