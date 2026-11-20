# Build

## Requirements

```text
Windows 10/11 x64
Python 3.12 x64
PySide6
PyInstaller 6.x
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Prepare external tools

This repository does **not** include third-party binaries.

Place:

```text
app/tools/payload-dumper.exe
app/tools/lpunpack.exe
app/tools/lpmake.exe
app/tools/simg2img.exe
app/tools/lpdump.exe
app/platform-tools/adb.exe
app/platform-tools/fastboot.exe
```

The tool also needs a matching resource pack (DA/Preloader/auth) at runtime.

## Build

```powershell
cd app

python -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name "MTK9400Pro" `
  --icon "icon.ico" `
  --distpath "v2_dist" `
  --workpath "v2_build" `
  --specpath "." `
  --paths ".." `
  --paths "." `
  --add-data "..\mtkclient\Loader\OPLUS_DA_mt6991.bin;mtkclient\Loader" `
  --add-data "..\mtkclient\Loader\OPLUS_mt6991.auth;mtkclient\Loader" `
  --add-data "..\mtkclient\payloads;mtkclient\payloads" `
  --add-data "..\mtkclient\Windows;mtkclient\Windows" `
  --add-data "..\mtkclient\Library\Filesystem\bin;mtkclient\Library\Filesystem\bin" `
  --add-data "icon.ico;." `
  --add-data "platform-tools;platform-tools" `
  --add-data "tools;tools" `
  launcher_v2.py
```

Output:

```text
app/v2_dist/MTK9400Pro.exe
```

## Selftest

```powershell
.\v2_dist\MTK9400Pro.exe --selftest
```

Expected:

```text
V2 RESULT : OK
```

## Tests

```powershell
python -m unittest discover -s tests -p "test_v2_*.py"
```

Expected:

```text
27 tests OK
```

## Missing blobs

The repository intentionally does not contain:

- firmware images
- resource packs
- third-party executables
- user backups

Build requires those files to be supplied locally.
