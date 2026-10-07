from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')


def test_source_pool_connections_doc_names_four_active_sources_and_latam_policy_disabled():
    path = ROOT / 'docs' / 'FLIGHT_SOURCE_POOL_CONNECTIONS.md'
    assert path.exists()
    body = path.read_text(encoding='utf-8').lower()
    for marker in ('clic', 'satena', 'jetsmart', 'wingo'):
        assert marker in body
    assert 'latam' in body
    assert 'robots_disallowed' in body
    assert 'deshabilitada' in body or 'disabled' in body
    assert 'verifica los horarios exactos con las aerolíneas' in body


def test_docs_describe_twenty_directions_ten_offer_target_and_status_semantics():
    docs = '\n'.join(read(rel).lower() for rel in (
        'docs/FLIGHT_SOURCE_POOL_CONNECTIONS.md', 'docs/ARCHITECTURE.md', 'docs/GRAPHQL.md', 'docs/DEMO_GUIDE.md', 'docs/COMPLIANCE.md'
    ))
    for marker in ('20 direcciones', '10 ofertas', 'available', 'partial', 'no_offers', 'source_unavailable'):
        assert marker in docs
    assert 'conexión sugerida' in docs or 'conexion sugerida' in docs
    assert 'no realiza reservas en los proveedores externos' in docs


def test_docs_keep_package_scope_direct_only_and_real_snapshot_fallback():
    docs = '\n'.join(read(rel).lower() for rel in ('README.md','docs/ARCHITECTURE.md','docs/DEMO_GUIDE.md','docs/FLIGHT_SOURCE_POOL_CONNECTIONS.md'))
    assert 'ghl' in docs and 'alkilautos' in docs
    assert 'direct' in docs
    assert 'snapshot' in docs
    assert 'stale_fallback' in docs
    assert 'mock provider' not in docs


def test_scraping_study_contains_coverage_and_baseline_evidence():
    sql = read('scripts/scraping_study.sql').lower()
    for marker in ('77', '20', 'least(', 'available', 'partial', 'no_offers', 'source_unavailable'):
        assert marker in sql
    for city in ('bog','mde','clo','ctg','smr'):
        assert city in sql
    for source in ('clicair','satena','jetsmart','wingo'):
        assert source in sql
    assert 'min(price)' in sql and 'avg(price)' in sql and 'max(price)' in sql
    assert 'candidate' in sql
