GPU engine sampling on this AMD NAS

The main FPK collector and CGI remain under the resmonpro package user.
GPU busy/temperature/VRAM come from read-only sysfs. Compute and Encoder use
DRM per-client engine counters, which require reading fdinfo across users.

One-time root setup:
python3 /var/apps/resmonpro/target/support/install-gpu-helper.py

This copies the reader to a root-owned directory and enables resmonpro-gpu.service.
The isolated reader has no network access and publishes only aggregate GPU numbers
in /run/resmonpro-gpu/engines.json. Missing/stale readings remain NULL, not zero.
The reader pauses when the FPK is stopped and exits when the FPK is removed.
To remove its boot registration: systemctl disable --now resmonpro-gpu.service

Existing readings are retained unchanged in SQLite; temperatures are rounded only
for display. GPU history starts when this version is installed. Unsupported GPU
sysfs metrics are left unavailable. Current integration is verified on AMD 780M.
