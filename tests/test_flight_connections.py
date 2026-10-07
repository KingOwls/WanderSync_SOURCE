from backend.gateway.flight_connections import build_suggested_connections


def leg(i, origin, destination, price, date="2026-10-27", source="jetsmart", currency="COP"):
    return {"id": f"f{i}", "origin": origin, "destination": destination, "travel_date": date, "price": price, "currency": currency, "source": source, "active": True}


def test_happy_path_builds_one_stop_candidate_and_preserves_legs():
    a=leg(1,"CTG","BOG",165000)
    b=leg(2,"BOG","SMR",180000,source="wingo")
    result=build_suggested_connections([a],[b],origin="CTG",destination="SMR",travel_date="2026-10-27")
    assert len(result)==1
    c=result[0]
    assert c.via=="BOG"
    assert c.total_price==345000
    assert c.currency=="COP"
    assert c.legs==(a,b)


def test_connection_rejects_invalid_pairs_and_allows_eoh_mde_same_via_city():
    valid_a=leg(1,"BOG","EOH",100000)
    valid_b=leg(2,"MDE","SMR",120000)
    assert build_suggested_connections([valid_a],[valid_b],origin="BOG",destination="SMR",travel_date="2026-10-27")[0].via=="MDE"
    assert not build_suggested_connections([leg(3,"BOG","CLO",1,date="2026-10-26")],[leg(4,"CLO","SMR",1)],origin="BOG",destination="SMR",travel_date="2026-10-27")
    assert not build_suggested_connections([leg(5,"BOG","CLO",1,currency="USD")],[leg(6,"CLO","SMR",1)],origin="BOG",destination="SMR",travel_date="2026-10-27")
    assert not build_suggested_connections([leg(7,"BOG","SMR",1)],[leg(8,"SMR","SMR",1)],origin="BOG",destination="SMR",travel_date="2026-10-27")
    assert not build_suggested_connections([leg(9,"BOG","CLO",1)],[leg(10,"MDE","SMR",1)],origin="BOG",destination="SMR",travel_date="2026-10-27")
    same=leg(11,"BOG","CLO",1)
    assert not build_suggested_connections([same],[same],origin="BOG",destination="SMR",travel_date="2026-10-27")


def test_connection_candidates_are_deterministic_and_capped_at_ten():
    outgoing=[]; incoming=[]
    vias=("CLO","MDE","CTG")
    n=1
    for via in vias:
        for j in range(4):
            outgoing.append(leg(n,"BOG", "EOH" if via=="MDE" else via,100000+j*1000,source="clicair")); n+=1
            incoming.append(leg(n, "MDE" if via=="MDE" else via,"SMR",120000+j*1000,source="wingo")); n+=1
    result=build_suggested_connections(outgoing,incoming,origin="BOG",destination="SMR",travel_date="2026-10-27")
    assert len(result)==10
    keys=[(x.total_price,x.via,x.legs[0]["source"],x.legs[1]["source"],x.legs[0]["id"],x.legs[1]["id"]) for x in result]
    assert keys==sorted(keys)
