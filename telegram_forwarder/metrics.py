import logging
from prometheus_client import Counter, Histogram, start_http_server

log = logging.getLogger(__name__)


class Metrics:
    def __init__(self, prefix: str = "tg_fwd"):
        self.received = Counter(
            f"{prefix}_messages_received_total",
            "Total messages seen on watched channels",
            ["channel_id"]
        )
        self.forwarded = Counter(
            f"{prefix}_messages_forwarded_total",
            "Messages matching rules and sent downstream",
            ["channel_id", "target"]
        )
        self.dropped = Counter(
            f"{prefix}_messages_dropped_total",
            "Messages ignored due to rules or empty body",
            ["channel_id", "reason"]
        )
        self.webhook_errors = Counter(
            f"{prefix}_webhook_errors_total",
            "HTTP delivery errors to configured webhook endpoints",
            ["endpoint", "status_code"]
        )
        self.latency = Histogram(
            f"{prefix}_processing_seconds",
            "Time spent evaluating rules and dispatching",
            buckets=(0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
        )


def run_metrics_server(port: int, host: str = "0.0.0.0") -> None:
    """Start standalone Prometheus scrapable HTTP endpoint."""
    try:
        start_http_server(port, addr=host)
        log.info("metrics exporting on %s:%d/metrics", host, port)
    except Exception as e:
        log.error("failed to bind metrics server on %s:%d: %s", host, port, e)
        raise
