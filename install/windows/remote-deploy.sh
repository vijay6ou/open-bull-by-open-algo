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

export SSHPASS="$PASS"
# Password goes through SSHPASS, not argv, so it is not echoed by shells.
SSH=(sshpass -e ssh
  -o StrictHostKeyChecking=accept-new
  -o UserKnownHostsFile="$HOME/.ssh/known_hosts"
  -o PreferredAuthentications=password
  -o PubkeyAuthentication=no
  -p "$PORT"
  "$USER@$HOST")

SCP=(sshpass -e scp
  -o StrictHostKeyChecking=accept-new
  -o UserKnownHostsFile="$HOME/.ssh/known_hosts"
  -o PreferredAuthentications=password
  -o PubkeyAuthentication=no
  -P "$PORT")

win_ps() {
  # Single-quoted remote command so local bash does not expand $variables.
  "${SSH[@]}" "powershell -NoProfile -ExecutionPolicy Bypass -Command $1"
}

echo "[INFO] Checking SSH ${USER}@${HOST}:${PORT}"
"${SSH[@]}" "hostname && whoami && echo OPENSSH_OK"

ENV_EXISTS="$(win_ps "'if (-not (Test-Path ''${APP_ROOT}'')) { New-Item -ItemType Directory -Force -Path ''${APP_ROOT}'' | Out-Null }; Write-Output (Test-Path ''${APP_ROOT}/.env'')'" | tr -d '[:space:]' | tail -n 1)"
echo "[INFO] VPS .env exists: ${ENV_EXISTS:-False}"

echo "[INFO] Packing project (excluding .env / venv / node_modules)"
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
echo "[INFO] Archive size: $(du -h "$STAGE/openbull.tgz" | awk '{print $1}')"

# Windows OpenSSH scp only reliably accepts paths under the user profile.
echo "[INFO] Uploading archive to Administrator home"
"${SCP[@]}" "$STAGE/openbull.tgz" "$USER@$HOST:openbull.tgz"

SEED_NAME=""
if [[ "$ENV_EXISTS" != "True" && -f "$ROOT/install/windows/.secrets.env" ]]; then
  echo "[INFO] VPS has no .env yet — uploading one-time key seed (not logged)"
  "${SCP[@]}" "$ROOT/install/windows/.secrets.env" "$USER@$HOST:openbull.secrets.env"
  SEED_NAME="openbull.secrets.env"
fi

echo "[INFO] Extracting on VPS"
win_ps "'
  \$ErrorActionPreference = \"Stop\"
  New-Item -ItemType Directory -Force -Path \"${APP_ROOT}\" | Out-Null
  \$homeTgz = Join-Path \$env:USERPROFILE \"openbull.tgz\"
  if (-not (Test-Path \$homeTgz)) { throw \"upload missing: \$homeTgz\" }
  tar -xzf \$homeTgz -C \"${APP_ROOT}\"
  \$installer = Join-Path \"${APP_ROOT}\" \"install\\windows\\Install-OpenBull.ps1\"
  if (-not (Test-Path \$installer)) { throw \"extract failed, missing \$installer\" }
  Write-Output \"EXTRACT_OK\"
  if (Test-Path (Join-Path \$env:USERPROFILE \"openbull.secrets.env\")) { Write-Output \"SEED_PRESENT\" }
'"

INSTALL_PS1="${APP_ROOT}/install/windows/Install-OpenBull.ps1"
UPDATE_PS1="${APP_ROOT}/install/windows/Update-OpenBull.ps1"

if [[ "$ENV_EXISTS" == "True" ]]; then
  echo "[INFO] Updating existing install (keys stay on the VPS)"
  "${SSH[@]}" "powershell -NoProfile -ExecutionPolicy Bypass -File ${UPDATE_PS1} -AppRoot ${APP_ROOT} -SkipGitPull"
else
  echo "[INFO] First-time install (this takes a while: Chocolatey, Postgres, Node, build)"
  if [[ -n "$SEED_NAME" ]]; then
    SEED_PATH="C:/Users/${USER}/openbull.secrets.env"
    "${SSH[@]}" "powershell -NoProfile -ExecutionPolicy Bypass -File ${INSTALL_PS1} -AppRoot ${APP_ROOT} -PublicHost ${PUBLIC_HOST} -SeedEnvFile ${SEED_PATH}"
  else
    "${SSH[@]}" "powershell -NoProfile -ExecutionPolicy Bypass -File ${INSTALL_PS1} -AppRoot ${APP_ROOT} -PublicHost ${PUBLIC_HOST}"
  fi
fi

win_ps "'
  Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path \$env:USERPROFILE \"openbull.tgz\")
  Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path \$env:USERPROFILE \"openbull.secrets.env\")
  Write-Output \"CLEANED_UPLOADS\"
'"

echo "[INFO] Deploy finished. Open http://${PUBLIC_HOST}/"
echo "[INFO] First visit: http://${PUBLIC_HOST}/setup"
