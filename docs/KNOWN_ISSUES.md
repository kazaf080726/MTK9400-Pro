# Known issues

## 1. No complete GPT in this repository

This repository contains source only. Firmware, rescue packages, complete scatter, `pgpt.bin`, `sgpt.bin` are not included.

A device with a destroyed GPT cannot be fully recovered from source alone.

## 2. GPT rebuild is not a stock copy

`gpt.py` can generate a GPT from a complete scatter, but:

- uses EFI Basic Data type
- generates random unique GUIDs
- does not preserve vendor attributes

Use a real GPT backup for normal recovery.

## 3. No hardware regression

Unit tests are computer-side only.

No real device test is included for:

- GPT restore
- raw write
- backup restore
- first boot

## 4. No firmware SHA verification by default

Firmware images are checked for existence and size, not cryptographic hash.

## 5. No per-partition read-back

Normal `w` writes are not read back and compared.

## 6. WinUSB

Some devices still fail with:

```text
USBError(32, 'Pipe error')
Could not read ME_ID
```

Prefer COM when available.

## 7. Third-party licensing

`payload-dumper.exe` is GPLv3.

If you redistribute a built binary, provide the corresponding source and license notices.

## 8. User data

The tool does not automatically back up:

```text
nvram
nvdata
persist
proinfo
seccfg
frp
misc
userdata
```
