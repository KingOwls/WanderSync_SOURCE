from backend.gateway.travel_logic import resolve_location


def test_mde_resolves_to_medellin_airports_without_rewriting_city_code():
    resolved = resolve_location("mde")
    assert resolved.city_code == "MDE"
    assert resolved.flight_airports == ("MDE", "EOH")
    assert resolved.service_city == "MDE"


def test_bog_and_unknown_locations_resolve_safely():
    bog = resolve_location("BOG")
    assert bog.flight_airports == ("BOG",)
    xyz = resolve_location("xyz")
    assert xyz.city_code == "XYZ"
    assert xyz.flight_airports == ("XYZ",)
    assert xyz.service_city == "XYZ"


def _flight(date_value, price, airline="CLIC", origin="BOG", destination="EOH", currency="COP"):
    return {
        "id": f"{airline}-{origin}-{destination}-{date_value}-{price}",
        "airline": airline,
        "origin": origin,
        "destination": destination,
        "travel_date": date_value,
        "price": price,
        "currency": currency,
    }


def test_availability_caps_real_dates_and_sorts_recommendations_by_lowest_flight_total():
    from backend.gateway.travel_logic import build_availability

    outbound = [_flight(f"2026-10-{day:02d}", 100000 + day * 1000) for day in range(10, 20)]
    returns = [_flight(f"2026-10-{day:02d}", 90000 + day * 500, origin="EOH", destination="BOG") for day in range(11, 25)]
    result = build_availability(outbound, returns)
    assert len(result.outbound_dates) == 8
    assert len(result.return_dates) == 8
    assert result.outbound_dates == tuple(sorted(result.outbound_dates))
    assert len(result.combinations) <= 12
    totals = [item.lowest_flight_total for item in result.combinations]
    assert totals == sorted(totals)


def test_availability_preserves_real_subset_and_one_airline_only():
    from backend.gateway.travel_logic import build_availability

    outbound = [_flight("2026-10-12", 120000), _flight("2026-10-14", 110000)]
    returns = [_flight("2026-10-15", 100000, origin="EOH", destination="BOG")]
    result = build_availability(outbound, returns)
    assert result.outbound_dates == ("2026-10-12", "2026-10-14")
    assert result.return_dates == ("2026-10-15",)
    assert len(result.combinations) == 2


def test_availability_enforces_one_to_fourteen_night_boundaries():
    from backend.gateway.travel_logic import build_availability

    outbound = [_flight("2026-10-10", 100000)]
    returns = [
        _flight("2026-10-10", 100000, origin="EOH", destination="BOG"),
        _flight("2026-10-11", 100000, origin="EOH", destination="BOG"),
        _flight("2026-10-24", 100000, origin="EOH", destination="BOG"),
        _flight("2026-10-25", 100000, origin="EOH", destination="BOG"),
    ]
    result = build_availability(outbound, returns)
    assert [(c.return_date, c.nights) for c in result.combinations] == [
        ("2026-10-11", 1),
        ("2026-10-24", 14),
    ]


def test_availability_handles_missing_outbound_or_missing_valid_return():
    from backend.gateway.travel_logic import build_availability

    empty = build_availability([], [_flight("2026-10-15", 100000, origin="EOH", destination="BOG")])
    assert empty.outbound_dates == () and empty.return_dates == () and empty.combinations == ()
    no_return = build_availability([_flight("2026-10-20", 100000)], [_flight("2026-10-10", 100000, origin="EOH", destination="BOG")])
    assert no_return.outbound_dates == ("2026-10-20",)
    assert no_return.combinations == ()


def test_roundtrip_package_builder_allows_mixed_airlines_and_sorts_by_total():
    from backend.gateway.travel_logic import build_roundtrip_packages

    outbound = [
        _flight("2026-10-10", 120000, airline="CLIC"),
        _flight("2026-10-10", 110000, airline="SATENA"),
    ]
    returns = [
        _flight("2026-10-13", 100000, airline="CLIC", origin="EOH", destination="BOG"),
        _flight("2026-10-13", 90000, airline="SATENA", origin="EOH", destination="BOG"),
    ]
    hotels = [{"id":"H1","nightly_price":200000,"currency":"COP"}]
    cars = [{"id":"C1","daily_price":100000,"currency":"COP"}]
    result = build_roundtrip_packages(outbound, returns, hotels, cars, nights=3, limit=12)
    assert len(result) == 4
    assert result[0].total == 110000 + 90000 + 200000*3 + 100000*3
    pairs = {(p.outbound["airline"], p.return_flight["airline"]) for p in result}
    assert ("CLIC", "SATENA") in pairs and ("SATENA", "CLIC") in pairs
    assert [p.total for p in result] == sorted(p.total for p in result)


def test_roundtrip_package_builder_requires_cop_and_both_legs():
    from backend.gateway.travel_logic import build_roundtrip_packages

    hotel = [{"id":"H1","nightly_price":200000,"currency":"COP"}]
    car = [{"id":"C1","daily_price":100000,"currency":"COP"}]
    assert build_roundtrip_packages([], [_flight("2026-10-11", 1, origin="EOH", destination="BOG")], hotel, car, 1) == []
    assert build_roundtrip_packages([_flight("2026-10-10", 1)], [], hotel, car, 1) == []
    usd = [_flight("2026-10-10", 1, currency="USD")]
    assert build_roundtrip_packages(usd, [_flight("2026-10-11", 1, origin="EOH", destination="BOG")], hotel, car, 1) == []


def test_all_five_tourist_locations_resolve_to_supported_airports_and_service_city():
    from backend.gateway.travel_logic import resolve_location

    expected = {
        "BOG": (("BOG",), "BOG"),
        "MDE": (("MDE", "EOH"), "MDE"),
        "CLO": (("CLO",), "CLO"),
        "CTG": (("CTG",), "CTG"),
        "SMR": (("SMR",), "SMR"),
    }
    for code, (airports, service_city) in expected.items():
        resolved = resolve_location(code)
        assert resolved.city_code == code
        assert resolved.flight_airports == airports
        assert resolved.service_city == service_city


def test_airport_to_tourist_city_mapping_consolidates_medellin_and_rejects_unknown():
    from backend.gateway.travel_logic import city_code_for_airport

    assert city_code_for_airport("EOH") == "MDE"
    assert city_code_for_airport("MDE") == "MDE"
    assert city_code_for_airport("BOG") == "BOG"
    assert city_code_for_airport("CLO") == "CLO"
    assert city_code_for_airport("CTG") == "CTG"
    assert city_code_for_airport("SMR") == "SMR"
    assert city_code_for_airport("XYZ") is None
