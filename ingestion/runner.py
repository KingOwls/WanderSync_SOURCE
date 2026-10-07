import os
import socket
import time

import httpx

from ingestion.flow import travel_scraping_flow
from ingestion.sources.registry import get_enabled_adapters

PREFECT_API_URL = os.getenv("PREFECT_API_URL", "http://prefect-server:4200/api")
DASK_SCHEDULER = os.getenv("DASK_SCHEDULER", "tcp://dask-scheduler:8786")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://wandersync:wandersync_dev_password@postgres:5432/wandersync")
INTERVAL = int(os.getenv("INGEST_INTERVAL_SECONDS", "900"))
RUN_ONCE = os.getenv("INGEST_RUN_ONCE", "false").lower() == "true"


def _database_ready() -> bool:
    try:
        import psycopg
        with psycopg.connect(DATABASE_URL, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def _internet_dns_ready() -> bool:
    hosts = []
    for adapter in get_enabled_adapters():
        hosts.extend(sorted(adapter.allowed_hosts))
    for host in hosts:
        try:
            socket.getaddrinfo(host, 443)
            return True
        except OSError:
            continue
    return False


def wait_for_dependencies():
    while True:
        prefect_ok = dask_ok = db_ok = dns_ok = False
        try:
            r = httpx.get(PREFECT_API_URL.rstrip("/") + "/health", timeout=3.0)
            prefect_ok = r.status_code < 500
        except Exception:
            pass
        try:
            from dask.distributed import Client
            with Client(DASK_SCHEDULER, timeout="3s") as client:
                # Wait for both configured workers, not merely the scheduler socket.
                dask_ok = len(client.scheduler_info().get("workers", {})) >= 2
        except Exception:
            pass
        db_ok = _database_ready()
        dns_ok = _internet_dns_ready()
        if prefect_ok and dask_ok and db_ok and dns_ok:
            print("Prefect, two Dask workers, PostgreSQL and public DNS are ready.")
            return
        print(f"Waiting: prefect={prefect_ok} dask_workers={dask_ok} postgres={db_ok} public_dns={dns_ok}")
        time.sleep(3)


if __name__ == "__main__":
    wait_for_dependencies()
    while True:
        try:
            travel_scraping_flow()
        except Exception as exc:
            print(f"Real scraping run failed after bounded retries: {exc}")
        if RUN_ONCE:
            break
        print(f"Next scraping ingestion in {INTERVAL} seconds")
        time.sleep(INTERVAL)
