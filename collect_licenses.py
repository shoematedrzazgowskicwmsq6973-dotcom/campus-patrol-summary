"""Retain installed third-party copyright and license notices in the release."""
import importlib.metadata as metadata
from pathlib import Path
import shutil
import sys

RUNTIME = ('rapidocr', 'onnxruntime', 'numpy', 'pillow', 'lxml', 'opencv-python-headless',
           'shapely', 'pyclipper', 'pyyaml', 'omegaconf', 'requests', 'certifi', 'charset-normalizer',
           'idna', 'urllib3', 'packaging', 'protobuf', 'flatbuffers', 'six', 'tqdm', 'colorlog', 'colorama')


def collect(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    index = ['Third-party components bundled with PatrolSummary', '']
    # Include the bootloader's license/exception along with runtime components.
    packages = list(RUNTIME)
    try:
        metadata.distribution('pyinstaller')
        packages.append('pyinstaller')
    except metadata.PackageNotFoundError:
        pass
    for name in packages:
        distribution = metadata.distribution(name)
        index.append(f'{distribution.metadata["Name"]} {distribution.version}')
        copied = 0
        for item in distribution.files or ():
            label = str(item).replace('\\', '/')
            upper_name = Path(label).name.upper()
            if any(word in upper_name for word in ('LICENSE', 'LICENCE', 'COPYING', 'NOTICE', 'COPYRIGHT')):
                source = Path(distribution.locate_file(item))
                if source.is_file():
                    package_root = (destination / name).resolve()
                    target = (package_root / label).resolve()
                    if not target.is_relative_to(package_root):
                        target = package_root / Path(label).name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                    copied += 1
        if copied == 0:
            # Some wheels put the complete license only in METADATA.
            (destination / f'{name}-METADATA.txt').write_text(distribution.read_text('METADATA') or '', encoding='utf-8')
    for python_license in (Path(sys.base_prefix) / 'LICENSE.txt', Path(sys.base_prefix) / 'LICENSE'):
        if python_license.is_file():
            shutil.copyfile(python_license, destination / 'Python-LICENSE.txt')
            break
    tkinter_license = Path(sys.base_prefix) / 'tcl'
    if tkinter_license.is_dir():
        for item in tkinter_license.rglob('license.terms'):
            target = destination / 'Tcl-Tk' / item.relative_to(tkinter_license)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, target)
    index += ['', 'OCR model attribution:',
        'Bundled OCR models are derived from official PaddleOCR models and distributed under Apache-2.0.',
        'RapidOCR authors: https://github.com/RapidAI/RapidOCR',
        'Upstream PaddleOCR: https://github.com/PaddlePaddle/PaddleOCR',
        'Model license statement: https://rapidai.github.io/RapidOCRDocs/main/en/model_licenses/',
        'Model files: PP-OCRv6_det_small.onnx, PP-OCRv6_rec_small.onnx, ch_ppocr_mobile_v2.0_cls_mobile.onnx',
        '', 'PyInstaller bootloader license and exception:',
        'https://pyinstaller.org/en/stable/license.html']
    (destination / 'INDEX.txt').write_text('\n'.join(index) + '\n', encoding='utf-8')


if __name__ == '__main__':
    collect(sys.argv[1])
