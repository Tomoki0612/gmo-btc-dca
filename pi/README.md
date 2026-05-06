# BTC DCA — Raspberry Pi 4 deployment

Self-hosted replacement for the AWS stack. Tailscale-only access, Discord
failure notifications, hourly cron-style purchase check, SQLite for state.

```
[Browser on tailnet]
        v   tailscale serve TLS
   [Caddy :80]
        ├─ /        → /opt/btc-dca/frontend/build (static)
        └─ /api/*   → 127.0.0.1:8000  (FastAPI/uvicorn)
                              ↕
                     /var/lib/btc-dca/dca.sqlite (WAL)

[run_purchase.py] ← btc-dca-purchase.timer (hourly, Persistent=true)
        ├─ schedule gate → SQLite dup guard → GMO Coin order
        └─ failures only → Discord webhook
```

## Prereqs (one-time on the Pi)

USB SSD boot is mandatory; microSD cards burn out under WAL writes.

```sh
sudo apt update
sudo apt install -y python3-venv python3-pip sqlite3 chrony caddy curl
chronyc tracking   # offset must be < 1s before going live
```

Install Tailscale per the official instructions, then:

```sh
sudo tailscale up
sudo tailscale serve --bg --https=443 http://127.0.0.1:80
```

## Layout on the Pi

```
/opt/btc-dca/
    pi/                 # this repo subtree (git clone)
    frontend/build/     # output of `npm run build`
    .venv/              # python venv (see below)
/var/lib/btc-dca/
    dca.sqlite          # WAL DB
    backups/            # daily `.backup` snapshots
/etc/btc-dca/
    secrets.env         # DISCORD_WEBHOOK_URL=...  (mode 0600, owner btcdca)
```

## Install

```sh
sudo useradd --system --home /opt/btc-dca --shell /usr/sbin/nologin btcdca
sudo install -d -o btcdca -g btcdca -m 0750 /opt/btc-dca /var/lib/btc-dca /etc/btc-dca
sudo -u btcdca git clone <repo> /opt/btc-dca/repo && sudo -u btcdca ln -s /opt/btc-dca/repo/pi /opt/btc-dca/pi
# alternative: rsync the `pi/` subtree directly

sudo -u btcdca python3 -m venv /opt/btc-dca/.venv
sudo -u btcdca /opt/btc-dca/.venv/bin/pip install -e /opt/btc-dca/pi
sudo -u btcdca /opt/btc-dca/.venv/bin/python -m pi.scripts.init_db /var/lib/btc-dca/dca.sqlite
```

Build frontend on a workstation, copy build output:

```sh
cd frontend && npm ci && npm run build
rsync -a build/ pi:/opt/btc-dca/frontend/build/
```

Caddy + systemd units:

```sh
sudo cp pi/caddy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy

sudo cp pi/systemd/*.service pi/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now btc-dca-api.service
sudo systemctl enable --now btc-dca-backup.timer
# Do NOT enable btc-dca-purchase.timer until the AWS-side EventBridge rule is Disabled.
```

Secrets:

```sh
echo 'DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...' | sudo install -m 0600 -o btcdca /dev/stdin /etc/btc-dca/secrets.env
```

## One-time data import from AWS

On a workstation with AWS CLI:

```sh
aws dynamodb scan --table-name btc-dca-settings --output json > settings.json
aws dynamodb scan --table-name btc-dca-history  --output json > history.json
scp settings.json history.json pi:/tmp/
ssh pi 'sudo -u btcdca /opt/btc-dca/.venv/bin/python -m pi.scripts.import_dynamo \
    --settings /tmp/settings.json --history /tmp/history.json --db /var/lib/btc-dca/dca.sqlite'
```

## Cutover

1. AWS Console → EventBridge → Rules → **Disable** `btc-auto-purchase-monthly`
2. AWS Console → Amplify Hosting → Build settings → **Disable** auto build
3. On the Pi: smoke test with `DRY_RUN=true sudo -u btcdca /opt/btc-dca/.venv/bin/python -m pi.purchase.run_purchase`
4. `sudo systemctl enable --now btc-dca-purchase.timer`
5. `systemctl list-timers btc-dca-*` to confirm the next firing time
6. Wait one full purchase cycle. After it succeeds, you're done.

## Verifying

```sh
# API
curl -s http://127.0.0.1:8000/api/settings | jq
curl -s http://127.0.0.1:8000/api/history  | jq '.items | length'
curl -s http://127.0.0.1:8000/api/balance  | jq

# Timer
systemctl list-timers btc-dca-purchase.timer
journalctl -u btc-dca-purchase.service --since '1 day ago'

# Backups
ls -la /var/lib/btc-dca/backups/

# Clock (HMAC drifts kill purchases)
chronyc tracking
```

## Failback to AWS

If the Pi is offline for an extended period:

1. AWS Console → EventBridge → **Enable** the purchase rule
2. AWS Console → Amplify Hosting → **Enable** auto build (if a frontend update is needed)
3. Sign in with Cognito at the Amplify URL
4. Re-enter `amount` / `frequency` / `scheduleDay` / `scheduleTime` / API key + secret on the settings screen — Pi-period changes don't sync to DynamoDB
5. Trigger Lambda Test once (with DRY_RUN=true) to confirm

When the Pi comes back, ensure `btc-dca-purchase.timer` is disabled while AWS
is the source of truth, and re-enable it only after disabling the EventBridge
rule again.

## Tests

```sh
python3 -m pytest pi/tests
```
