from pathlib import Path


def test_snapshots_package_is_in_shared_ingestion_build_context():
    for name in ("__init__.py", "manager.py", "metadata.py"):
        assert (Path("ingestion/snapshots") / name).exists()
    dockerfile = Path("ingestion/Dockerfile").read_text()
    assert "COPY . /app/ingestion" in dockerfile


def test_prefect_server_and_client_are_pinned_to_same_version():
    requirements = Path("ingestion/requirements.txt").read_text()
    compose = Path("docker-compose.yml").read_text()
    assert "prefect==3.8.8" in requirements
    assert "prefecthq/prefect:3.8.8-python3.12" in compose


def test_dask_scheduler_workers_and_runner_share_same_ingestion_build_context():
    compose = Path("docker-compose.yml").read_text()
    for service in ("dask-scheduler:", "dask-worker-1:", "dask-worker-2:", "ingestion-runner:"):
        assert service in compose
    assert compose.count("build: ./ingestion") >= 4
