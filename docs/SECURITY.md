# Security

## Path handling

All external names go through `app/v2/paths.py`:

- `safe_name`
- `safe_join`
- `safe_extract_zip`

ZIP rules:

- reject `..`
- reject absolute paths
- reject symlinks
- max 20000 files
- max 64 GB

## GPT writes

GPT write must:

1. validate source
2. save current GPT
3. compare capacity/sector/GUID
4. write backup GPT
5. write primary GPT
6. read back and verify

## Flash writes

- preflight
- explicit confirmation for critical partitions
- raw mode requires backup or explicit confirmation
- logical partitions blocked
- preloader/GPT images only in expert mode
- never automatically write nvram/nvdata/persist

## Commands

`subprocess` uses argument lists, no `shell=True`.

## Sensitive data

Do not commit:

```text
nvram
nvdata
persist
proinfo
seccfg
frp
misc
userdata
IMEI
calibration
logs
```

## Third-party

- payload-dumper-go: GPLv3
- AOSP lp tools: Apache/AOSP
- Qt/PySide6: LGPLv3
- OPLUS DA/auth: device maintenance only

See `THIRD_PARTY_NOTICES.md`.

## Reporting

Open a GitHub issue with:

- tool version
- connection mode
- device model
- exact log
- steps to reproduce

Do not post IMEI, serial numbers, nvram, or personal data.
