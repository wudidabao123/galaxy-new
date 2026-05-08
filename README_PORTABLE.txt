Galaxy New Portable
===================

First run:
  1. Double-click setup.bat and enter the model API key.
  2. Double-click start.bat for local access.
  3. Double-click start_public.bat to start a Cloudflare quick tunnel.

Local URL:
  http://localhost:8502

Public tunnel:
  start_public.bat prints an https://*.trycloudflare.com URL in the console.

Data folders:
  workspace\   agent-created files, uploads, generated outputs
  galaxy.db    local app database
  .keys\       local API-key fallback if Windows Credential Manager is unavailable

Do not share a configured package unless you intentionally want to share its API keys.
