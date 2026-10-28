# Troubleshooting

- CGC not found: select the absolute cgc.exe path from the working upstream Python virtual environment; its adjacent python.exe must exist.
- Destination succeeds, staging fails: set STAGING_NEO4J_PASSWORD in .env and run `docker compose up -d` in HamtayarDemo. Check `docker compose logs --tail=100`. Do not change destination ports.
- Changed Docker password but authentication fails: NEO4J_AUTH only initializes a new database. Existing volumes retain their previous password. Do not delete volumes containing needed data.
- Index failed: inspect sanitized job logs, confirm language support and check the actual CGC command help via Settings. Unsupported archives can contain readable files without code declarations.
- Model returns no evidence: use actual symbol names or paths; this release does not provide multilingual vector search.
- Port occupied: stop only application-owned processes using stop-dev.ps1; do not terminate unrelated services.
- PowerShell native execution fails: use a regular non-administrator terminal. The scripts invoke virtual-environment executables directly, so activation is unnecessary. Apply your organization's script execution policy; no policy bypass is required by this project.
- Restart backend after changing startup limits. Connections can be updated in Settings when no job runs.

- RAR decoder missing: install UnRAR or 7-Zip and enter its full executable path under Settings → RAR_UNRAR_TOOL / RAR_7ZIP_TOOL. WinRAR and 7-Zip under Program Files are detected automatically. ZIP uploads do not require either tool. Split or password-protected RAR files must be repacked as one unencrypted archive.
