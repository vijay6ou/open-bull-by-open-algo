# OpenBull on a Windows VPS

These scripts install the full stack (PostgreSQL, Redis, Python, Node, Caddy) as Windows services and keep broker keys on the VPS so later updates never ask for them.

## One-time prep (you)

1. RDP into the Windows VPS as Administrator.
2. Copy `Enable-OpenSSH.ps1` there, or open **elevated** PowerShell and run:

   ```powershell
   Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
   Start-Service sshd
   Set-Service -Name sshd -StartupType Automatic
   New-NetFirewallRule -DisplayName "OpenSSH SSH Server (sshd)" -Direction Inbound -Protocol TCP -LocalPort 22 -Action Allow
   New-NetFirewallRule -DisplayName "OpenBull HTTP" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow
   ```

3. In your VPS provider panel, allow inbound **TCP 22** and **TCP 80**.
4. Save these **once** as Cursor environment secrets (future agents reuse them):
   - `WINDOWS_VPS_HOST` — public IP or hostname
   - `WINDOWS_VPS_USER` — usually `Administrator`
   - `WINDOWS_VPS_PASSWORD` — RDP/Administrator password
   - `WINDOWS_VPS_SSH_PORT` — optional, default `22`
   - `WINDOWS_VPS_PUBLIC_HOST` — optional public URL/IP if different from the SSH host

Do not paste those values into GitHub or chat. After they are saved, ask the agent to deploy.

## What the agent runs

```bash
install/windows/remote-deploy.sh
```

- First run: installs dependencies, writes `C:\openbull\.env` **once**, starts services.
- Later runs: syncs code, migrates, rebuilds the frontend, restarts services. **`.env` is never overwritten.**

## Manual install on the VPS (optional)

From an elevated PowerShell in the repo:

```powershell
.\install\windows\Install-OpenBull.ps1 -PublicHost YOUR_VPS_IP
.\install\windows\Update-OpenBull.ps1
```

Open `http://YOUR_VPS_IP/setup` for the first admin account.

## Start / stop the whole program

From an elevated Command Prompt or PowerShell on the VPS:

```bat
openbull start
openbull stop
openbull restart
openbull status
```

Desktop shortcuts **OpenBull start** and **OpenBull stop** are also created.

## Services

| Service           | Role                                      |
| ----------------- | ----------------------------------------- |
| `OpenBullBackend` | FastAPI + WebSocket proxy (`uv`/uvicorn)  |
| `OpenBullCaddy`   | HTTP :80 → frontend + API + `/ws`         |
| `OpenBullRedis`   | Local Redis on `127.0.0.1:6379`           |
| `postgresql*`     | Database `openbull`                       |

Logs: `C:\openbull\logs\`.
