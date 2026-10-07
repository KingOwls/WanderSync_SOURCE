from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / 'docker-compose.yml'


def load_compose():
    return yaml.safe_load(COMPOSE.read_text())


def test_compose_has_no_mock_provider_or_provider_url():
    compose = load_compose()
    assert 'provider-service' not in compose['services']
    assert 'PROVIDER_URL' not in COMPOSE.read_text()


def test_scraping_services_share_snapshots_and_exact_productive_source_defaults():
    compose = load_compose()
    assert 'scrape_snapshots' in compose['volumes']
    expected_sources = '${SCRAPE_ENABLED_SOURCES:-clicair,satena,jetsmart,wingo,ghl_porton_medellin,alkilautos_national_medellin}'
    for service_name in ('ingestion-runner', 'dask-worker-1', 'dask-worker-2'):
        service = compose['services'][service_name]
        assert 'scrape_snapshots:/data/snapshots' in service.get('volumes', [])
        assert service['environment']['PYTHONPATH'] == '/app'
        assert service['environment']['SCRAPE_ENABLED_SOURCES'] == expected_sources
        assert service['environment']['TARGET_OFFERS_PER_DIRECTION'] == '${TARGET_OFFERS_PER_DIRECTION:-10}'
        assert service['environment']['MAX_ROUTE_CONCURRENCY_PER_SOURCE'] == '${MAX_ROUTE_CONCURRENCY_PER_SOURCE:-2}'


def test_scheduler_workers_runner_share_identical_ingestion_build_and_prefect_version_parity():
    compose = load_compose()
    for service_name in ('dask-scheduler', 'dask-worker-1', 'dask-worker-2', 'ingestion-runner'):
        assert compose['services'][service_name]['build'] == './ingestion'
    requirements = (ROOT / 'ingestion/requirements.txt').read_text().lower()
    assert 'prefect==3.8.8' in requirements
    assert '3.8.8' in str(compose['services']['prefect-server']['image'])


def test_ingestion_snapshot_package_is_preserved_for_distributed_serialization():
    for rel in ('ingestion/snapshots/__init__.py','ingestion/snapshots/manager.py','ingestion/snapshots/metadata.py'):
        assert (ROOT / rel).exists()
    dockerfile = (ROOT / 'ingestion/Dockerfile').read_text(encoding='utf-8')
    assert 'COPY . /app/ingestion' in dockerfile
