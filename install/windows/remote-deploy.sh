#!/usr/bin/env bash
# Deploy or update OpenBull on the Windows VPS from a Linux Cloud Agent.
# Uses Cursor environment secrets. Does not print or overwrite live keys.
#
# Required env:
#   WINDOWS_VPS_HOST
#   WINDOWS_VPS_USER
#   WINDOWS_VPS_PASSWORD
# Optional env:
#   WINDOWS_VPS_SSH_PORT   (default 22)
#   WINDOWS_VPS_PUBLIC_HOST
#   WINDOWS_VPS_APP_ROOT   (default C:/openbull)
#
# Broker keys are seeded only when the VPS has no .env yet, from:
#   1) process env (BROKER_API_KEY / JAINAMXTS_*)
#   2) install/windows/.secrets.env on this agent (gitignored)

set -euo pipefail

HOST="${WINDOWS_VPS_HOST:-}"
USER="${WINDOWS_VPS_USER:-}"
PASS="${WINDOWS_VPS_PASSWORD:-}"
PORT="${WINDOWS_VPS_SSH_PORT:-22}"
APP_ROOT="${WINDOWS_VPS_APP_ROOT:-C:/openbull}"
PUBLIC_HOST="${WINDOWS_VPS_PUBLIC_HOST:-$HOST}"

if [[ -z "$HOST" || -z "$USER" || -z "$PASS" ]]; then
  echo "WINDOWS_VPS_HOST, WINDOWS_VPS_USER, and WINDOWS_VPS_PASSWORD must be set." >&2
  echo "Add them once as Cursor environment secrets, then re-run." >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if ! command -v sshpass >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y sshpass
fi

SSH=(sshpass -p "$PASS" ssh
  -o StrictHostKeyChecking=accept-new
  -o UserKnownHostsFile="$HOME/.ssh/known_hosts"
  -o PreferredAuthentications=password
  -o PubkeyAuthentication=no
  -p "$PORT"
  "$USER@$HOST")

SCP=(sshpass -p "$PASS" scp
  -o StrictHostKeyChecking=accept-new
  -o UserKnownHostsFile="$HOME/.ssh/known_hosts"
  -o PreferredAuthentications=password
  -o PubkeyAuthentication=no
  -P "$PORT")

echo "[INFO] Checking SSH ${USER}@${HOST}:${PORT}"
"${SSH[@]}" "hostname && whoami && echo OPENSSH_OK"

WIN_ROOT="${APP_ROOT//\//\\}"
"${SSH[@]}" "powershell -NoProfile -Command \"if (-not (Test-Path '$APP_ROOT')) { New-Item -ItemType Directory -Force -Path '$APP_ROOT' | Out-Null }; Write-Output (Test-Path '$APP_ROOT\\.env')\"" > /tmp/openbull-vps-env-exists.txt
ENV_EXISTS="$(tr -d '[:space:]' < /tmp/openbull-vps-env-exists.txt | tail -n 1)"

echo "[INFO] Syncing project to $APP_ROOT (excluding .env / venv / node_modules)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
tar --exclude='.git' \
    --exclude='.env' \
    --exclude='.venv' \
    --exclude='venv' \
    --exclude='node_modules' \
    --exclude='frontend/dist' \
    --exclude='frontend/node_modules' \
    --exclude='logs' \
    --exclude='backups' \
    --exclude='install/windows/.secrets.env' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    -czf "$STAGE/openbull.tgz" .

"${SCP[@]}" "$STAGE/openbull.tgz" "$USER@$HOST:C:/Windows/Temp/openbull.tgz"

SEED_ARG=""
if [[ "$ENV_EXISTS" != "True" && -f "$ROOT/install/windows/.secrets.env" ]]; then
  echo "[INFO] VPS has no .env yet — uploading one-time key seed (not logged)"
  "${SCP[@]}" "$ROOT/install/windows/.secrets.env" "$USER@$HOST:C:/Windows/Temp/openbull.secrets.env"
  SEED_ARG="-SeedEnvFile C:/Windows/Temp/openbull.secrets.env"
fi

"${SSH[@]}" "powershell -NoProfile -ExecutionPolicy Bypass -Command \"
  \$ErrorActionPreference = 'Stop'
  New-Item -ItemType Directory -Force -Path '$APP_ROOT' | Out-Null
  tar -xf C:/Windows/Temp/openbull.tgz -C '$APP_ROOT'
  if (Test-Path C:/Windows/Temp/openbull.secrets.env) { Write-Output 'SEED_PRESENT' }
\""

INSTALL_PS1="$APP_ROOT/install/windows/Install-OpenBull.ps1"
UPDATE_PS1="$APP_ROOT/install/windows/Update-OpenBull.ps1"

if [[ "$ENV_EXISTS" == "True" ]]; then
  echo "[INFO] Updating existing install (keys stay on the VPS)"
  "${SSH[@]}" "powershell -NoProfile -ExecutionPolicy Bypass -File $UPDATE_PS1 -AppRoot $APP_ROOT -SkipGitPull"
else
  echo "[INFO] First-time install"
  "${SSH[@]}" "powershell -NoProfile -ExecutionPolicy Bypass -File $INSTALL_PS1 -AppRoot $APP_ROOT -PublicHost $PUBLIC_HOST $SEED_ARG"
  "${SSH[@]}" "powershell -NoProfile -Command \"Remove-Item -Force -ErrorAction SilentlyContinue C:/Windows/Temp/openbull.secrets.env\""
fi

"${SSH[@]}" "powershell -NoProfile -Command \"Remove-Item -Force -ErrorAction SilentlyContinue C:/Windows/Temp/openbull.tgz\""

echo "[INFO] Deploy finished. Open http://${PUBLIC_HOST}/"
echo "[INFO] First visit: http://${PUBLIC_HOST}/setup"
