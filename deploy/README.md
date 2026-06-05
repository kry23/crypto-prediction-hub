# deploy/

Production deployment artifacts for the Hetzner host.

## Layout

- `systemd/` — three .service unit files for the scheduler, UI, and
  intel-bridge processes.
- `install_systemd_units.sh` — root script: copies the units to
  `/etc/systemd/system/`, runs `daemon-reload`, enables + starts.

## Prerequisites (handled by the cutover runbook)

- `/opt/crypto-predictor` exists, owned by `crypto-predictor:crypto-predictor`
- `/etc/crypto-predictor/secrets.env` exists, mode 0640, owned by
  `root:crypto-predictor`
- venv at `/opt/crypto-predictor/venv` with `pip install -e ".[dev]"`
- PostgreSQL 16 running locally, `DATABASE_URL` set in secrets.env

## Install

```bash
sudo bash /opt/crypto-predictor/deploy/install_systemd_units.sh
```

## Update after `git pull`

```bash
ssh crypto-predictor "cd /opt/crypto-predictor && git pull && \
    sudo systemctl restart crypto-predictor-scheduler \
                            crypto-predictor-ui \
                            crypto-predictor-intel-bridge"
```

## Logs

```bash
journalctl -u crypto-predictor-scheduler -n 100 -f
journalctl -u crypto-predictor-ui --since "10 minutes ago"
```

## Stop one for maintenance

```bash
sudo systemctl stop crypto-predictor-ui
# ... do work ...
sudo systemctl start crypto-predictor-ui
```
