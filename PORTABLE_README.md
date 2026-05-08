# Galaxy New Portable Packaging

This repository can build a Windows portable package that includes:

- Galaxy New source code
- Embedded Python runtime
- Installed Python dependencies from `requirements.txt`
- One-click setup/start/stop scripts
- `cloudflared.exe` copied from `C:\Users\26043\Desktop\cloudflared-windows-amd64.exe`

## Build

Double-click:

```bat
build_portable.bat
```

Or run manually:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_portable.ps1
```

The output is:

```text
dist\GalaxyNewPortable\
dist\GalaxyNewPortable.zip
```

## Use On Another PC

1. Unzip `GalaxyNewPortable.zip`.
2. Double-click `setup.bat` and enter the model API key.
3. Double-click `start.bat` for local access.
4. Double-click `start_public.bat` to expose it through Cloudflare quick tunnel.

The public launcher prints an `https://*.trycloudflare.com` URL in the console.

## Notes

Configured packages contain local data and may contain API-key fallback files. Share the fresh package before running `setup.bat`, or remove `.keys`, `.env`, and `galaxy.db` before sharing.
