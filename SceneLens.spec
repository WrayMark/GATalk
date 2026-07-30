# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project_root = Path(SPECPATH)

a = Analysis(
    [str(project_root / 'src' / 'scenelens' / '__main__.py')],
    pathex=[str(project_root / 'src')],
    binaries=[],
    datas=[
        (
            str(
                project_root
                / 'src'
                / 'scenelens'
                / 'modules'
                / 'asset_breakdown'
                / 'config'
                / 'scene_profiles.json'
            ),
            'scenelens/modules/asset_breakdown/config',
        ),
        (
            str(
                project_root
                / 'src'
                / 'scenelens'
                / 'modules'
                / 'asset_breakdown'
                / 'schemas'
                / '*.json'
            ),
            'scenelens/modules/asset_breakdown/schemas',
        ),
        (
            str(
                project_root
                / 'src'
                / 'scenelens'
                / 'modules'
                / 'artwork_study'
                / 'config'
                / 'presets.json'
            ),
            'scenelens/modules/artwork_study/config',
        ),
        (
            str(
                project_root
                / 'src'
                / 'scenelens'
                / 'modules'
                / 'artwork_study'
                / 'schemas'
                / '*.json'
            ),
            'scenelens/modules/artwork_study/schemas',
        ),
        (
            str(
                project_root
                / 'src'
                / 'scenelens'
                / 'modules'
                / 'visual_review'
                / 'config'
                / 'presets.json'
            ),
            'scenelens/modules/visual_review/config',
        ),
        (
            str(
                project_root
                / 'src'
                / 'scenelens'
                / 'modules'
                / 'visual_review'
                / 'schemas'
                / '*.json'
            ),
            'scenelens/modules/visual_review/schemas',
        ),
        (
            str(
                project_root
                / 'src'
                / 'scenelens'
                / 'providers'
                / 'config'
                / 'providers.json'
            ),
            'scenelens/providers/config',
        ),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'pytest', 'scipy'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SceneLens',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    upx=False,
    upx_exclude=[],
    name='SceneLens',
)
