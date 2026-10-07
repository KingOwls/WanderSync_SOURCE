from backend.gateway.travel_logic import build_travel_network


def _row(origin, destination, count, sources, first_date, last_date, lowest_price):
    return {"origin":origin,"destination":destination,"offer_count":count,"sources":sources,"first_date":first_date,"last_date":last_date,"lowest_price":lowest_price}


def test_network_collapses_medellin_airports_and_keeps_all_twenty_pairs():
    rows=[
        _row("EOH","CLO",3,["clicair"],"2026-10-10","2026-10-20",150000),
        _row("MDE","CLO",2,["jetsmart"],"2026-10-12","2026-11-01",140000),
        _row("CLO","EOH",4,["clicair","satena"],"2026-10-15","2026-11-05",130000),
    ]
    network=build_travel_network(rows,{})
    assert network.cities == ("BOG","MDE","CLO","CTG","SMR")
    assert len(network.routes)==20
    by={(r.origin,r.destination):r for r in network.routes}
    mde_clo=by[("MDE","CLO")]
    assert mde_clo.raw_offer_count==5 and mde_clo.visible_offer_count==5 and mde_clo.coverage_status=="PARTIAL"
    assert mde_clo.sources == ("clicair","jetsmart")
    assert by[("BOG","SMR")].outbound_available is False


def test_network_package_flag_requires_roundtrip_hotel_and_car():
    rows=[_row("BOG","EOH",2,["clicair"],"2026-10-10","2026-10-20",150000),_row("EOH","BOG",2,["satena"],"2026-10-11","2026-10-21",160000)]
    network=build_travel_network(rows,{"MDE":(True,True)})
    by={(r.origin,r.destination):r for r in network.routes}
    assert by[("BOG","MDE")].package_available is True
    assert by[("BOG","CLO")].package_available is False


def test_network_zero_pair_distinguishes_no_offers_from_unavailable():
    healthy={s:"SUCCESS" for s in ("clicair","satena","jetsmart","wingo")}
    network=build_travel_network([],{},healthy)
    by={(r.origin,r.destination):r for r in network.routes}
    assert by[("BOG","SMR")].coverage_status=="NO_OFFERS"
    healthy["wingo"]="SOURCE_UNAVAILABLE"
    network=build_travel_network([],{},healthy)
    by={(r.origin,r.destination):r for r in network.routes}
    assert by[("BOG","SMR")].coverage_status=="SOURCE_UNAVAILABLE"
