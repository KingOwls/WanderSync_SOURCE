from ingestion.parsers.hotels import parse_hotels
from ingestion.models import SnapshotMetadata


def metadata(source):
    return SnapshotMetadata(source, 'hotels', 'https://public.example/rooms', 'query', '2030-01-01T00:00:00+00:00', 200, 'SUCCESS')


def test_ghl_paragraph_titles_and_prices_stay_inside_each_card():
    html = '''<h1>Habitaciones Hotel GHL Collection 93 en Bogotá</h1>
    <div class="rooms-aquarius__description"><p class="rooms-aquarius__title">Collection</p><p class="rooms-aquarius__price-value">470.000 COP</p></div>
    <div class="rooms-aquarius__description"><p class="rooms-aquarius__title">Superior</p><p class="rooms-aquarius__price-value">360.450 COP</p></div>
    <div class="rooms-aquarius__description"><p class="rooms-aquarius__title">Sin precio</p></div>'''
    rows = parse_hotels(html, metadata('ghl_bogota'))
    assert [(r['room_type'],r['price_text']) for r in rows] == [('Collection','470.000 COP'),('Superior','360.450 COP')]
    assert all(r['city'] == 'Bogotá' for r in rows)
    assert all(r['name'] == 'Hotel GHL Collection 93' for r in rows)


def test_spiwak_room_cards_do_not_mix_promotional_prices():
    html = '''<h1>Habitaciones Spiwak Chipichape en Cali</h1>
    <div class="rooms-crux__description"><p class="description__title--rooms-crux">Luxury King Suite</p><p class="rooms-crux__value">663.708 COP</p></div>
    <div class="offers"><h4>Early Booking</h4>Desde 64.638 COP</div>'''
    rows = parse_hotels(html, metadata('spiwak_cali'))
    assert len(rows) == 1
    assert rows[0]['price_text'] == '663.708 COP'
    assert rows[0]['city'] == 'Cali'
