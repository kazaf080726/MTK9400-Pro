# Architecture

## Structure

```text
launcher_v2.py
  → PyInstaller onefile
  → app/v2/main.py
  → --mtk forwards to mtk.py
```

## Connection

Modes:

```text
Auto (COM preferred)
WinUSB only
COM only
```

`app/core/mtk_session.py` runs a persistent:

```text
MTK9400_Pro.exe --mtk ... server
```

One Preloader/DA handshake, multiple `r/w/wo/ro/e` commands.

## V2 modules

| File | Responsibility |
|---|---|
| `app/v2/main.py` | main window, connection, progress, GPT UI |
| `app/v2/gpt.py` | GPT parse/build/restore |
| `app/v2/backup.py` | manifest, SHA256, restore plan |
| `app/v2/backup_page.py` | backup/restore UI |
| `app/v2/firmware.py` | scatter/ZIP/OFP/payload/super |
| `app/v2/flash_page.py` | deep flash UI |
| `app/v2/ofp.py` | OFP decrypt |
| `app/v2/payload.py` | payload-dumper wrapper |
| `app/v2/lptools.py` | lpunpack/lpmake/simg2img |
| `app/v2/sparse.py` | sparse expand |
| `app/v2/paths.py` | path/ZIP safety |
| `app/v2/workers.py` | background QThread |
| `app/v2/theme.py` | light/dark theme |

## GPT

- 512/4096 sector
- protective MBR
- primary/backup GPT
- CRC32
- GPT restore: backup first, primary second, read-back verify
- GPT rebuild from complete scatter requires `pgpt`/`sgpt`
- generated GPT uses EFI Basic Data and random unique GUIDs

## Backup

Manifest fields:

```text
format, version, created, model, platform
sector_size, total_sectors, disk_size, disk_guid, gpt
items[]: name, file, size, sha256, group, start_lba, size_bytes
```

Restore:

```text
GPT readable   → w name file
GPT unreadable → wo start_lba*sector_size size file
```

## Firmware

Sources:

```text
scatter dir
ZIP with scatter or payload
OFP
payload.bin
super dir
```

Safety:

- safe ZIP extraction
- reject `..`, absolute path, symlink
- 64 GB and 20000 file limits
- logical partitions blocked from direct write
- payload materialized lazily in a background thread

## Commands

```text
r  partition file
w  partition file
wo offset length file
ro offset length file
e  partition
es partition
```

## Progress

`run_sequence()` displays:

```text
step i/n
partition name
file size
live server stage
```

## Build

PyInstaller onefile. Required data:

```text
mtkclient/Loader/*
mtkclient/payloads/*
mtkclient/Windows/*
mtkclient/Library/Filesystem/bin/*
app/tools/*
app/platform-tools/*
app/icon.ico
```
