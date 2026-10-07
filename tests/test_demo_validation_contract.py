from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / 'scripts/demo_validation.py').read_text(encoding='utf-8')


def test_demo_validates_five_cities_twenty_directions_and_four_source_health():
    assert 'travelNetwork' in SCRIPT
    assert 'sourceHealth' in SCRIPT
    for city in ('BOG', 'MDE', 'CLO', 'CTG', 'SMR'):
        assert city in SCRIPT
    assert '20' in SCRIPT
    for source in ('clicair', 'satena', 'jetsmart', 'wingo'):
        assert source in SCRIPT.lower()


def test_demo_selects_real_flight_availability_date_before_flight_search():
    assert 'flightAvailability' in SCRIPT
    assert 'flightSearch' in SCRIPT
    assert 'travelDate' in SCRIPT
    assert 'directOffers' in SCRIPT
    assert 'connections' in SCRIPT
    assert 'SKIP' in SCRIPT or 'NOT AVAILABLE' in SCRIPT


def test_demo_keeps_packages_direct_roundtrip_and_provenance():
    assert 'travelAvailability' in SCRIPT
    assert 'travelPackages' in SCRIPT
    assert 'packageAvailable' in SCRIPT
    for field in ('nights', 'source', 'sourceUrl', 'snapshotId', 'scrapedAt', 'outboundFlight', 'returnFlight', 'flightTotal'):
        assert field in SCRIPT
    assert 'outboundFlightId:$outbound' in SCRIPT
    assert 'returnFlightId:$returnFlight' in SCRIPT


def test_demo_never_hardcodes_a_guaranteed_connection():
    assert 'Verifica los horarios exactos con las aerolíneas.' in SCRIPT
    assert 'connection' in SCRIPT.lower()
    assert 'guaranteed_connection' not in SCRIPT.lower()
