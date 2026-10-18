# Build only from the sanitized public-source directory.
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas = [('resources', 'resources')]
binaries = []
hiddenimports = []
for package in ('rapidocr', 'onnxruntime', 'omegaconf'):
    package_data, package_binaries, package_imports = collect_all(package)
    datas += package_data
    binaries += package_binaries
    hiddenimports += package_imports
datas += copy_metadata('rapidocr')

a = Analysis(['app_entry.py'], pathex=[], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, hookspath=[], runtime_hooks=[],
             excludes=['torch', 'tensorflow', 'paddle', 'openvino', 'tensorrt', 'matplotlib', 'pytest', 'IPython'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='PatrolSummary',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='PatrolSummary')
