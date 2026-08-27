# Third-party notices

This document covers the Qt for Python components redistributed in the verified
Windows package of Game Automation Control Plane. The Control Plane source code
and original project artwork are licensed separately under the
[GNU Affero General Public License v3.0 only](LICENSE).

## Qt for Python / PySide6 6.11.2

The Windows package is built from the official PyPI distributions of:

- PySide6 6.11.2;
- PySide6-Essentials 6.11.2;
- PySide6-Addons 6.11.2; and
- Shiboken6 6.11.2.

Those packages include Qt 6.11.2 runtime libraries used by the application.
Qt for Python is offered under the LGPL-3.0-only, GPL, or Qt commercial terms.
This project redistributes the unmodified community binaries under the
LGPL-3.0-only option.

Copyright belongs to The Qt Company Ltd, the Qt Project contributors, and the
respective third-party component authors.

License texts supplied with this package:

- [`licenses/LGPL-3.0-only.txt`](licenses/LGPL-3.0-only.txt)
- [`licenses/GPL-3.0-only.txt`](licenses/GPL-3.0-only.txt), whose terms are
  incorporated by LGPL version 3

Official project and licensing information:

- https://doc.qt.io/qtforpython-6/
- https://doc.qt.io/qtforpython-6.9/licenses.html
- https://doc.qt.io/qt-6/licensing.html

Corresponding source for the pinned binary version:

- PySide6 6.11.2 source:
  https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/pyside-setup-everywhere-src-6.11.2.tar.xz
- Qt 6.11.2 source, including module-specific third-party notices:
  https://download.qt.io/archive/qt/6.11/6.11.2/single/qt-everywhere-src-6.11.2.tar.xz

The onedir Windows package keeps Qt and PySide6 libraries as separate files
under `_internal/PySide6`. It does not prevent replacement of those libraries.
An ABI-compatible build may be substituted in that directory; keep the same
filenames and directory layout. The Control Plane source needed to rebuild the
application is in this repository.

The official Qt source archives are the authoritative source for component-level
copyright and attribution notices. Only modules collected by PyInstaller are
redistributed in the Windows package.
