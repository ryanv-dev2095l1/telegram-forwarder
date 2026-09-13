# telegram-forwarder

A small daemon I run on my home server to watch a few high-volume Telegram channels, filter out junk with regular expressions, and re-post matches to private group chats or webhook endpoints.

## Setup

1. Python 3.11+ required.
2. Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

3. Create your `config.yaml` from the example:

```bash
cp config.example.yaml config.yaml
```

Get your Telegram API credentials from https://my.telegram.org. Put `api_id` and `api_hash` in `config.yaml`.

## Running

First run will ask for your phone number and Telegram verification code to write the session file:

```bash
python -m telegram_forwarder --config config.yaml
```

Once logged in, the session persists in `session_forwarder.session`.

## Metrics

When `metrics.enabled` is set to `true`, a Prometheus scrape target runs at `http://0.0.0.0:9102/metrics` exposing:
- `tg_messages_received_total`
- `tg_messages_matched_total`
- `tg_forwards_sent_total`
- `tg_webhook_failures_total`

## Systemd service

To run in background on Debian/Ubuntu:

```ini
[Unit]
Description=Telegram Channel Forwarder
After=network.target

[Service]
Type=simple
User=alex
WorkingDirectory=/opt/telegram-forwarder
ExecStart=/opt/telegram-forwarder/.venv/bin/tg-forwarder --config /opt/telegram-forwarder/config.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Testing

```bash
pytest
```

<!-- last-sync: 2026-09-13 -->
