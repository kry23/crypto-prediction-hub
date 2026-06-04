# Cutover Runbook — Windows → Hetzner Migration

> **For the operator (Koray):** This is an OPERATIONAL runbook, NOT subagent-driven. You execute the steps in your PowerShell terminal + Hetzner panel + Cloudflare panel; I help by writing the commands and (after T+105) by SSH-ing into the server to run commands on your behalf when invited.
>
> Steps use checkbox (`- [ ]`) syntax for tracking. Estimated total: ~3.5 hours. Rollback any time before T+195 by re-enabling the Windows Task Scheduler.

**Goal:** Migrate the crypto-predictor scheduler + data + UI to a persistent Hetzner VPS in a single ~3.5-hour cutover with zero data loss. After this runbook, the Windows scheduler is decommissioned and the cloud server runs 24/7.

**Architecture (from spec §1):** Hetzner CPX11 Falkenstein Ubuntu 24.04, PostgreSQL 16, systemd services for scheduler + UI + intel-bridge + cloudflared, Cloudflare Tunnel + Access for HTTPS + auth.

**Tech Stack:** PowerShell (local), bash (Hetzner SSH), Python 3.12, PostgreSQL 16, systemd, Cloudflare Tunnel.

**Spec reference:** `docs/superpowers/specs/2026-06-05-web-ui-cloud-migration-design.md` §2.

**Scheduling constraint:** Do NOT span 06:00 UTC. Recommended start time: 12:00 UTC or later. Ends well before next 06:00 UTC.

---

## Pre-cutover (day before, ~30 min)

- [ ] **Step 1: Order Hetzner CPX11 ahead of time**

  https://console.hetzner.cloud → New project → "crypto-predictor" → Add Server:
  - Location: **Falkenstein**
  - Image: **Ubuntu 24.04**
  - Type: **CPX11** (2 vCPU, 4 GB RAM, 40 GB SSD, €4.85/mo)
  - SSH key: **upload now** (next step)
  - Name: `crypto-predictor`

- [ ] **Step 2: Generate SSH keypair (PowerShell)**

  ```powershell
  ssh-keygen -t ed25519 -f $HOME\.ssh\hetzner_key -C "crypto-predictor"
  # Passphrase: optional; if used, you'll be prompted on first ssh; can use ssh-agent later
  ```

  Then read the public key:

  ```powershell
  Get-Content $HOME\.ssh\hetzner_key.pub
  ```

  Copy the full `ssh-ed25519 AAAA...` line and paste it into the Hetzner SSH-key field during Step 1.

- [ ] **Step 3: Verify Hetzner is provisioned + note the IPv4**

  After ~1-2 minutes, the server shows up in your Hetzner project with an IPv4 address (e.g., `5.78.x.x`). Note it down: `HETZNER_IP=______________`.

- [ ] **Step 4: First SSH login from PowerShell (accept host key)**

  ```powershell
  ssh -i $HOME\.ssh\hetzner_key root@HETZNER_IP
  # Type yes when asked to accept host key
  # Once you see the Ubuntu shell, type: exit
  ```

  This pre-trusts the server host key so my later SSH commands don't prompt.

- [ ] **Step 5: Append SSH config so I can reach the box too**

  ```powershell
  @"

  Host crypto-predictor
      HostName HETZNER_IP
      User crypto-predictor
      IdentityFile ~/.ssh/hetzner_key
      StrictHostKeyChecking accept-new
  "@ | Add-Content $HOME\.ssh\config
  ```

  After we create the `crypto-predictor` deploy user (Step 13), I can use `ssh crypto-predictor "..."` from my Bash tool.

- [ ] **Step 6: Make sure Cloudflare account exists**

  https://dash.cloudflare.com → sign in (or sign up). If you don't have a domain yet:

  https://dash.cloudflare.com/?to=/:account/domains → Register `kry.app` (or similar) → ~$9 + ICANN fee. Wait for activation (usually instant for new .app TLDs).

  Note your Cloudflare email + the chosen domain: `DOMAIN=______________`.

---

## Cutover phase A — Hetzner base + SSH access (T+0 → T+45, ~45 min)

- [ ] **Step 7 (T+0): STOP the Windows Task Scheduler FIRST**

  ```powershell
  Stop-ScheduledTask -TaskName CryptoPredictorScheduler
  # Verify:
  Get-ScheduledTask -TaskName CryptoPredictorScheduler | Get-ScheduledTaskInfo | Select-Object LastTaskResult
  # LastTaskResult should NOT be 267009 (TASK_STATE_RUNNING) anymore
  ```

  **Why first**: avoid double-fire of 06:00 UTC scan during migration (spec §7 risk register).

- [ ] **Step 8 (T+2): Backup local SQLite once more for safety**

  ```powershell
  cd C:\Users\Koray\Desktop\crypto-predictor
  .\.venv\Scripts\python.exe scripts\backup_databases.py
  # Should produce a fresh snapshot under ~/.crypto-predictor-backups/
  ```

- [ ] **Step 9 (T+5): SSH to Hetzner as root**

  ```powershell
  ssh -i $HOME\.ssh\hetzner_key root@HETZNER_IP
  ```

  From here, you are on the **Hetzner box** in a bash shell. Subsequent steps marked `[server]` run there; `[local]` run back in PowerShell on your laptop.

- [ ] **Step 10 [server] (T+6): Set hostname + timezone + apt update**

  ```bash
  hostnamectl set-hostname crypto-predictor
  timedatectl set-timezone UTC
  apt update && apt -y upgrade
  ```

  This first `apt upgrade` can take 5–10 minutes.

- [ ] **Step 11 [server] (T+15): Install all packages we need**

  ```bash
  apt install -y \
      python3.12 python3.12-venv python3-pip \
      postgresql-16 postgresql-client-16 \
      nginx git curl \
      build-essential libpq-dev
  ```

- [ ] **Step 12 [server] (T+25): Install cloudflared (Cloudflare Tunnel daemon)**

  ```bash
  curl -L --output cloudflared.deb \
      https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
  dpkg -i cloudflared.deb
  rm cloudflared.deb
  cloudflared --version  # verify
  ```

- [ ] **Step 13 [server] (T+27): Create the deploy user**

  ```bash
  useradd -m -s /bin/bash crypto-predictor
  mkdir -p /home/crypto-predictor/.ssh
  cp ~/.ssh/authorized_keys /home/crypto-predictor/.ssh/authorized_keys
  chown -R crypto-predictor:crypto-predictor /home/crypto-predictor/.ssh
  chmod 700 /home/crypto-predictor/.ssh
  chmod 600 /home/crypto-predictor/.ssh/authorized_keys
  ```

  Now I can reach the box as `crypto-predictor` user via the SSH config alias from Step 5.

- [ ] **Step 14 [server] (T+32): Grant restricted sudo for service restarts**

  ```bash
  cat > /etc/sudoers.d/crypto-predictor << 'EOF'
  crypto-predictor ALL=(root) NOPASSWD: /bin/systemctl restart crypto-predictor-scheduler
  crypto-predictor ALL=(root) NOPASSWD: /bin/systemctl restart crypto-predictor-ui
  crypto-predictor ALL=(root) NOPASSWD: /bin/systemctl restart crypto-predictor-intel-bridge
  crypto-predictor ALL=(root) NOPASSWD: /bin/systemctl status crypto-predictor-*
  EOF
  chmod 440 /etc/sudoers.d/crypto-predictor
  visudo -c -f /etc/sudoers.d/crypto-predictor  # verify syntax
  ```

- [ ] **Step 15 [local] (T+35): Test the SSH alias from my Bash tool**

  Back in PowerShell, ask me to verify:

  > "Can you ssh crypto-predictor and run `uname -a`?"

  I'll run `ssh crypto-predictor "uname -a"` from my Bash tool. If output is `Linux crypto-predictor 6.x ...`, the SSH access loop is closed and the rest of the cutover can flow through me + you in parallel.

---

## Cutover phase B — Code + PostgreSQL (T+45 → T+105, ~60 min)

- [ ] **Step 16 [server, as root] (T+45): Clone the repo + venv**

  From PowerShell, hand over to me:

  > "Run the clone + venv setup."

  I run (as root, then chown so the deploy user can manage the tree):

  ```bash
  ssh root@HETZNER_IP 'mkdir -p /opt/crypto-predictor && \
    chown crypto-predictor:crypto-predictor /opt/crypto-predictor'
  ssh root@HETZNER_IP 'sudo -u crypto-predictor git clone \
    https://github.com/kry23/crypto-prediction-hub.git /opt/crypto-predictor'
  ssh root@HETZNER_IP 'cd /opt/crypto-predictor && \
    sudo -u crypto-predictor python3.12 -m venv venv && \
    sudo -u crypto-predictor ./venv/bin/pip install -e ".[dev]"'
  ```

  ~5-10 min for pip install (numpy, pandas, scikit-learn pull lots of wheels).

- [ ] **Step 17 [server, as root] (T+60): Initialize PostgreSQL**

  ```bash
  sudo -u postgres createuser --pwprompt crypto_predictor
  # Enter a strong password; save it for /etc/crypto-predictor/secrets.env later
  sudo -u postgres createdb -O crypto_predictor crypto_predictor
  ```

- [ ] **Step 18 [server, as root] (T+62): Configure pg_hba.conf for localhost password auth**

  ```bash
  # Find the conf file:
  PG_HBA=$(sudo -u postgres psql -t -c "SHOW hba_file;" | xargs)
  echo "Found pg_hba: $PG_HBA"

  # Add line above the default 'host all all' rules:
  sed -i '/^# IPv4 local connections:/a host crypto_predictor crypto_predictor 127.0.0.1\/32 scram-sha-256' "$PG_HBA"
  systemctl reload postgresql
  ```

- [ ] **Step 19 [server, as root] (T+65): Apply PG tuning (spec §3)**

  Edit `/etc/postgresql/16/main/postgresql.conf`:

  ```bash
  cat >> /etc/postgresql/16/main/postgresql.conf << 'EOF'

  # crypto-predictor tuning
  shared_buffers = 1GB
  effective_cache_size = 2GB
  max_connections = 50
  work_mem = 16MB
  EOF
  systemctl restart postgresql
  ```

- [ ] **Step 20 [server, as crypto-predictor] (T+70): Run the SQLite → PostgreSQL migration script**

  This script is created during the UI build plan (Task 1.5 of the UI plan), so on cutover day we expect it to already be in the repo. If it isn't yet (we're cutting over earlier than UI ship), defer Step 20 and copy the SQLite files as-is in Step 21; then run the migration once UI build delivers the script.

  ```bash
  cd /opt/crypto-predictor
  ./venv/bin/python scripts/migrate_sqlite_to_postgres.py \
      --predictions ./predictions.db \
      --sentiment ./data/sentiment_cache.db \
      --global ./data/global_cache.db \
      --pg "postgresql://crypto_predictor:PASSWORD@127.0.0.1:5432/crypto_predictor"
  ```

  Expected output: per-table row counts with `OK: X rows migrated` and a final parity report.

- [ ] **Step 21 [local, PowerShell] (T+80): scp the data files from Windows to Hetzner**

  ```powershell
  cd C:\Users\Koray\Desktop\crypto-predictor

  # SQLite DBs (small — predictions.db ~few MB, caches even smaller)
  scp -i $HOME\.ssh\hetzner_key predictions.db crypto-predictor@HETZNER_IP:/opt/crypto-predictor/
  scp -i $HOME\.ssh\hetzner_key data\sentiment_cache.db crypto-predictor@HETZNER_IP:/opt/crypto-predictor/data/
  scp -i $HOME\.ssh\hetzner_key data\global_cache.db crypto-predictor@HETZNER_IP:/opt/crypto-predictor/data/

  # Configuration files
  scp -i $HOME\.ssh\hetzner_key data\scheduler_config.yaml crypto-predictor@HETZNER_IP:/opt/crypto-predictor/data/
  scp -i $HOME\.ssh\hetzner_key data\equity_blacklist.yaml crypto-predictor@HETZNER_IP:/opt/crypto-predictor/data/
  scp -i $HOME\.ssh\hetzner_key data\mcap_ranks.yaml crypto-predictor@HETZNER_IP:/opt/crypto-predictor/data/
  scp -i $HOME\.ssh\hetzner_key data\sector_map.yaml crypto-predictor@HETZNER_IP:/opt/crypto-predictor/data/
  scp -i $HOME\.ssh\hetzner_key data\tilt_weights_phase_1_5.yaml crypto-predictor@HETZNER_IP:/opt/crypto-predictor/data/
  scp -i $HOME\.ssh\hetzner_key data\calibration_1_5_4.json crypto-predictor@HETZNER_IP:/opt/crypto-predictor/data/

  # Parquet history — this is the big one (~3 GB)
  # -r recurses, scp will show progress per file
  scp -i $HOME\.ssh\hetzner_key -r data\history crypto-predictor@HETZNER_IP:/opt/crypto-predictor/data/
  ```

  ~15-20 min depending on your upload bandwidth.

- [ ] **Step 22 [server] (T+100): Set up `/etc/crypto-predictor/secrets.env`**

  Ask me to run from your terminal:

  > "Help me write the secrets.env"

  I produce:

  ```bash
  ssh crypto-predictor 'sudo mkdir -p /etc/crypto-predictor && sudo chown root:crypto-predictor /etc/crypto-predictor && sudo chmod 750 /etc/crypto-predictor'
  ```

  Then YOU directly (because secrets shouldn't pass through my context):

  ```powershell
  ssh crypto-predictor
  # Now in bash on the server:
  sudo tee /etc/crypto-predictor/secrets.env > /dev/null << 'EOF'
  DATABASE_URL=postgresql://crypto_predictor:YOUR_PG_PASSWORD@127.0.0.1:5432/crypto_predictor
  TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID=YOUR_CHAT_ID
  NEWSAPI_API_KEY=YOUR_NEWSAPI_KEY
  ANTHROPIC_API_KEY=
  CLOUDFLARE_TUNNEL_TOKEN=PLACEHOLDER_FILLED_AT_STEP_24
  CLAUDE_DAILY_USD_LIMIT=5
  EOF
  sudo chown root:crypto-predictor /etc/crypto-predictor/secrets.env
  sudo chmod 640 /etc/crypto-predictor/secrets.env
  exit
  ```

  (Copy values from your local `data/secrets.env`. `ANTHROPIC_API_KEY` can stay empty; we fill it when Ask Claude tab is ready.)

---

## Cutover phase C — systemd services + Cloudflare Tunnel (T+105 → T+150, ~45 min)

- [ ] **Step 23 [server, via me]: Install systemd unit files**

  Hand over to me:

  > "Install the three systemd units."

  I run a sequence that writes the units (templates from spec §1) to `/etc/systemd/system/`, then `daemon-reload`, then `enable + start`.

  Unit files I'll write (precise contents in the UI build plan Task 6.1):

  - `crypto-predictor-scheduler.service` — `ExecStart=/opt/crypto-predictor/venv/bin/python scripts/run_scheduler.py`
  - `crypto-predictor-ui.service` — placeholder until UI is built; `ExecStart=/bin/sleep infinity` for now
  - `crypto-predictor-intel-bridge.service` — placeholder until intel-bridge is built

  Each with `EnvironmentFile=/etc/crypto-predictor/secrets.env`, `User=crypto-predictor`, `Restart=on-failure`, `RestartSec=30`.

  Then:

  ```bash
  systemctl daemon-reload
  systemctl enable --now crypto-predictor-scheduler
  systemctl status crypto-predictor-scheduler  # should show 'active (running)'
  ```

- [ ] **Step 24 [browser]: Set up Cloudflare Tunnel via panel**

  https://one.dash.cloudflare.com/ → Networks → Tunnels → Create a tunnel:
  - Connector: **Cloudflared**
  - Name: `crypto-predictor`
  - Copy the **tunnel token** (long base64 string)
  - **Save** but don't yet add a public hostname

  Add the tunnel token to `/etc/crypto-predictor/secrets.env` (you do this via ssh; I avoid the value):

  ```powershell
  ssh crypto-predictor
  sudo nano /etc/crypto-predictor/secrets.env
  # Replace CLOUDFLARE_TUNNEL_TOKEN= line with the token from Cloudflare panel
  ```

  Then install + start cloudflared (I run for you):

  ```bash
  ssh crypto-predictor 'sudo cloudflared service install $(sudo grep CLOUDFLARE_TUNNEL_TOKEN /etc/crypto-predictor/secrets.env | cut -d= -f2)'
  ssh crypto-predictor 'sudo systemctl enable --now cloudflared'
  ```

- [ ] **Step 25 [browser]: Add public hostname routing**

  Same Cloudflare panel → your new tunnel → **Public Hostname** tab → Add:
  - Subdomain: `predictor`
  - Domain: your registered domain (e.g., `kry.app`)
  - Service: `http://localhost:8501`
  - Save.

  DNS propagates within seconds (Cloudflare-managed zone).

- [ ] **Step 26 [browser]: Cloudflare Access policy**

  https://one.dash.cloudflare.com/ → Access → Applications → Add an application:
  - Type: **Self-hosted**
  - Name: `crypto-predictor`
  - Domain: `predictor.kry.app`
  - Save.

  Then add a policy:
  - Name: `me-only`
  - Action: **Allow**
  - Include: **Emails** → `kkorkmaz1881@gmail.com`
  - Save.

  Now opening `https://predictor.kry.app` from any browser prompts for the magic link.

---

## Cutover phase D — Smoke test (T+150 → T+195, ~45 min)

- [ ] **Step 27 [via me]: Smoke `predict_scan_cli.py` end-to-end**

  ```bash
  ssh crypto-predictor 'cd /opt/crypto-predictor && ./venv/bin/python scripts/predict_scan_cli.py'
  ```

  Expected:
  - Reads `data/scheduler_config.yaml` → `mode=shadow`
  - Sends Telegram scan-start heartbeat
  - Runs ~340-symbol scan
  - Persists ~340 rows to PG with `mode='shadow'`
  - Renders `reports/predict-YYYY-MM-DD-HHMM.md` with `🔬 SHADOW Daily Report` title
  - Sends Telegram post-scan summary

  Validate: row count in PG matches scan size.

- [ ] **Step 28 [via me]: Row count parity check**

  ```bash
  ssh crypto-predictor 'PGPASSWORD=$(sudo grep DATABASE_URL /etc/crypto-predictor/secrets.env | sed -n "s/.*:\\(.*\\)@.*/\\1/p") \
    psql -h 127.0.0.1 -U crypto_predictor -d crypto_predictor -c \
    "SELECT mode, COUNT(*) FROM predictions GROUP BY mode ORDER BY 1;"'
  ```

  Compare against Windows snapshot from Step 8.

- [ ] **Step 29 [browser]: UI smoke test**

  Open https://predictor.kry.app on your phone or laptop.
  - Cloudflare Access prompt appears
  - Enter your email → check inbox → click magic link
  - Returns to the UI
  - All 4 tabs render (Dashboard, Track Record, Operator, Ask Claude)
  - Dashboard shows today's slate (the scan we just ran)
  - Ask Claude can be skipped if `ANTHROPIC_API_KEY` is still empty; a banner explains how to fill it

- [ ] **Step 30 [via me]: scheduler_running event check**

  ```bash
  ssh crypto-predictor 'sudo journalctl -u crypto-predictor-scheduler --since "5 minutes ago"'
  ```

  Confirm `scheduler_running` event with all 6 cron jobs + `timezone: UTC`.

---

## Cutover phase E — Decommission Windows (T+195 → T+210, ~15 min)

- [ ] **Step 31 [local PowerShell]: Uninstall the Windows task**

  ```powershell
  cd C:\Users\Koray\Desktop\crypto-predictor
  pwsh -File scripts\uninstall_windows_scheduler.ps1
  ```

  Expected: "Unregistering task 'CryptoPredictorScheduler'... Done."

- [ ] **Step 32 [local PowerShell]: Verify it's gone**

  ```powershell
  Get-ScheduledTask -TaskName CryptoPredictorScheduler -ErrorAction SilentlyContinue
  # Should return nothing
  ```

- [ ] **Step 33 [Telegram]: Send the announcement message**

  Either from Hetzner via me:

  > "Send the migration-complete announcement."

  Or manually from your Telegram client:

  ```
  🚀 Migrated to predictor.kry.app
  Scheduler now runs on Hetzner.
  UI: https://predictor.kry.app
  ```

- [ ] **Step 34: Update CHANGELOG.md + commit operational state**

  ```bash
  ssh crypto-predictor 'cd /opt/crypto-predictor && git pull'
  ```

  From local PowerShell, add a CHANGELOG entry + commit:

  ```powershell
  cd C:\Users\Koray\Desktop\crypto-predictor
  # Edit CHANGELOG.md: add "Migrated to Hetzner CPX11 + Streamlit v1.0" section
  git add CHANGELOG.md
  git commit -m "ops: cutover to Hetzner predictor.kry.app"
  git push
  ssh crypto-predictor 'cd /opt/crypto-predictor && git pull && sudo systemctl restart crypto-predictor-scheduler'
  ```

---

## Rollback (any time before T+195)

If anything breaks irrecoverably:

```powershell
# Re-enable Windows Task Scheduler:
cd C:\Users\Koray\Desktop\crypto-predictor
pwsh -File scripts\install_windows_scheduler.ps1
Start-ScheduledTask -TaskName CryptoPredictorScheduler
```

Then investigate the Hetzner failure separately; reschedule cutover for another day.

## Post-cutover (first 24 hours)

- [ ] **Watch tomorrow's 06:00 UTC predict_scan fire**: Telegram heartbeat + summary land
- [ ] **Watch tomorrow's 06:30 UTC validate_pending**: closes any matured shadow predictions
- [ ] **Watch tomorrow's 06:45 UTC backup_databases**: produces a backup in `/var/lib/crypto-predictor/backups/`
- [ ] **Backup restore smoke test** (within the first week):

  ```bash
  ssh crypto-predictor 'PGPASSWORD=... psql -h 127.0.0.1 -U postgres -d postgres -c "CREATE DATABASE test_restore;"'
  ssh crypto-predictor 'gunzip -c /var/lib/crypto-predictor/backups/pg_*.sql.gz | PGPASSWORD=... psql -h 127.0.0.1 -U postgres -d test_restore'
  ssh crypto-predictor 'PGPASSWORD=... psql -h 127.0.0.1 -U postgres -d test_restore -c "SELECT COUNT(*) FROM predictions;"'
  ssh crypto-predictor 'PGPASSWORD=... psql -h 127.0.0.1 -U postgres -d postgres -c "DROP DATABASE test_restore;"'
  ```

  Row count should match production.

## Definition of done

- All 34 steps complete
- Tomorrow morning the Hetzner-hosted scheduler fires 06:00 UTC scan → Telegram heartbeat lands from the server
- `https://predictor.kry.app` is reachable + Cloudflare Access gates the UI
- Windows Task Scheduler is unregistered
- Journal section 25 added on cutover day documenting the live migration + any deviations from this runbook
