import sys
import time

import httpx

URL = "http://localhost:8000/graphql"
SUPPORTED_CITIES = {"BOG", "MDE", "CLO", "CTG", "SMR"}
ACTIVE_SOURCES = {"clicair", "satena", "jetsmart", "wingo"}
PREFERRED_PACKAGE_ROUTE = ("BOG", "MDE")
CONNECTION_WARNING = "Verifica los horarios exactos con las aerolíneas."


def call(client, query, variables=None, allow_error=False):
    response = client.post(URL, json={"query": query, "variables": variables or {}})
    payload = response.json()
    if (not response.is_success or payload.get("errors")) and not allow_error:
        raise RuntimeError(f"GraphQL failure HTTP {response.status_code}: {payload}")
    return response, payload


def require_provenance(item, label):
    missing = [key for key in ("source", "sourceUrl", "snapshotId", "scrapedAt") if not item.get(key)]
    if missing:
        raise AssertionError(f"{label} missing provenance: {missing}")


def get_package_availability(client, origin, destination):
    query = '''
    query($origin:String!,$destination:String!){
      travelAvailability(origin:$origin,destination:$destination,outboundLimit:8,returnLimit:8){
        airportCodes outboundDates returnDates combinations{departureDate returnDate nights lowestFlightTotal}
      }
    }'''
    return call(client, query, {"origin": origin, "destination": destination})[1]["data"]["travelAvailability"]


def get_flight_availability(client, origin, destination):
    query = '''
    query($origin:String!,$destination:String!){
      flightAvailability(origin:$origin,destination:$destination){
        dates{travelDate directOfferCount connectionCandidateCount}
      }
    }'''
    return call(client, query, {"origin": origin, "destination": destination})[1]["data"]["flightAvailability"]


def get_flight_search(client, origin, destination, travel_date):
    query = '''
    query($origin:String!,$destination:String!,$travelDate:String!){
      flightSearch(origin:$origin,destination:$destination,travelDate:$travelDate,limit:50){
        status availableCount
        directOffers{id airline origin destination travelDate price source sourceUrl snapshotId scrapedAt}
        connections{via stops totalPrice currency warning legs{id airline origin destination travelDate price source sourceUrl snapshotId scrapedAt}}
      }
    }'''
    return call(client, query, {"origin": origin, "destination": destination, "travelDate": travel_date})[1]["data"]["flightSearch"]


def main():
    email = f"demo-{int(time.time())}@wandersync.local"
    password = "WanderSync123!"
    with httpx.Client(timeout=30.0) as client:
        print("[1] Session Fixation")
        before = call(client, "query { sessionInfo { sessionPrefix } }")[1]["data"]["sessionInfo"]["sessionPrefix"]
        call(client, "mutation($e:String!,$n:String!,$p:String!){register(email:$e,fullName:$n,password:$p){id}}", {"e": email, "n": "Demo User", "p": password})
        call(client, "mutation($e:String!,$p:String!){login(email:$e,password:$p){id}}", {"e": email, "p": password})
        after = call(client, "query { sessionInfo { sessionPrefix authenticated } }")[1]["data"]["sessionInfo"]
        assert before != after["sessionPrefix"] and after["authenticated"]

        print("[2] Fuente productiva y salud")
        health = call(client, "query { sourceHealth { activeCount totalCount sources { source status available itemsFound } } }")[1]["data"]["sourceHealth"]
        assert health["totalCount"] == 4
        assert {row["source"] for row in health["sources"]} == ACTIVE_SOURCES
        print(f"    active={health['activeCount']}/4")

        print("[3] travelNetwork: cinco ciudades y 20 direcciones")
        network = call(client, '''query { travelNetwork {
          cities{code name airports}
          routes{origin destination coverageStatus visibleOfferCount rawOfferCount packageAvailable outboundAvailable}
        }}''')[1]["data"]["travelNetwork"]
        assert {c["code"] for c in network["cities"]} == SUPPORTED_CITIES
        assert len(network["routes"]) == 20
        print("    20 directions OK")

        print("[4] Direct flight demo from real flightAvailability")
        direct_demo = None
        for route in network["routes"]:
            if not route["outboundAvailable"]:
                continue
            availability = get_flight_availability(client, route["origin"], route["destination"])
            option = next((d for d in availability["dates"] if d["directOfferCount"] > 0), None)
            if option:
                result = get_flight_search(client, route["origin"], route["destination"], option["travelDate"])
                if result["directOffers"]:
                    direct_demo = result
                    for item in result["directOffers"]:
                        require_provenance(item, "direct flight")
                    print(f"    direct offers={len(result['directOffers'])}, date={option['travelDate']}")
                    break
        assert direct_demo is not None, "ensure real scraping ingestion completed before demo"

        print("[5] Suggested connection demo when current external data supports one")
        connection_demo = None
        for route in network["routes"]:
            if route["visibleOfferCount"] > 0:
                continue
            availability = get_flight_availability(client, route["origin"], route["destination"])
            option = next((d for d in availability["dates"] if d["connectionCandidateCount"] > 0), None)
            if not option:
                continue
            result = get_flight_search(client, route["origin"], route["destination"], option["travelDate"])
            if result["connections"]:
                connection_demo = result["connections"][0]
                assert connection_demo["stops"] == 1 and connection_demo["warning"] == CONNECTION_WARNING
                for leg in connection_demo["legs"]:
                    require_provenance(leg, "connection leg")
                print(f"    via={connection_demo['via']} total={connection_demo['totalPrice']} {CONNECTION_WARNING}")
                break
        if connection_demo is None:
            print("    SKIP / NOT AVAILABLE: current catalog has no same-date one-stop candidate")

        print("[6] Direct-only package demo")
        package_route = next((r for r in network["routes"] if r["origin"] == PREFERRED_PACKAGE_ROUTE[0] and r["destination"] == PREFERRED_PACKAGE_ROUTE[1] and r["packageAvailable"]), None)
        package_route = package_route or next((r for r in network["routes"] if r["packageAvailable"]), None)
        if package_route is None:
            print("    SKIP / NOT AVAILABLE: no packageAvailable route")
        else:
            availability = get_package_availability(client, package_route["origin"], package_route["destination"])
            if not availability["combinations"]:
                print("    SKIP / NOT AVAILABLE: package route has no 1-14 night combination")
            else:
                selected = availability["combinations"][0]
                package_query = '''query($origin:String!,$destination:String!,$s:String!,$e:String!){
                  travelPackages(origin:$origin,destination:$destination,startDate:$s,endDate:$e,limit:12){
                    total flightTotal nights
                    outboundFlight{id source sourceUrl snapshotId scrapedAt}
                    returnFlight{id source sourceUrl snapshotId scrapedAt}
                    hotel{id source sourceUrl snapshotId scrapedAt}
                    car{id source sourceUrl snapshotId scrapedAt}
                  }}'''
                packages = call(client, package_query, {"origin": package_route["origin"], "destination": package_route["destination"], "s": selected["departureDate"], "e": selected["returnDate"]})[1]["data"]["travelPackages"]
                assert packages
                package = packages[0]
                for key in ("outboundFlight", "returnFlight", "hotel", "car"):
                    require_provenance(package[key], key)
                checkout_query = "mutation($outbound:String!,$returnFlight:String!,$h:String!,$c:String!,$n:Int!,$t:Float!,$x:String){checkoutPackage(outboundFlightId:$outbound,returnFlightId:$returnFlight,hotelId:$h,carId:$c,nights:$n,total:$t,simulateFailure:$x){id status paymentStatus}}"
                variables = {"outbound": package["outboundFlight"]["id"], "returnFlight": package["returnFlight"]["id"], "h": package["hotel"]["id"], "c": package["car"]["id"], "n": package["nights"], "t": package["total"], "x": None}
                happy = call(client, checkout_query, variables)[1]["data"]["checkoutPackage"]
                assert happy["status"] == "CONFIRMED"
                failed_vars = dict(variables); failed_vars["x"] = "return_flight"
                failed = call(client, checkout_query, failed_vars)[1]["data"]["checkoutPackage"]
                assert failed["status"] == "CANCELLED"
                events = call(client, "query($id:String!){sagaEvents(orderId:$id){step action status}}", {"id": failed["id"]})[1]["data"]["sagaEvents"]
                assert any(e["action"] == "COMPENSATE" and e["status"] == "SUCCEEDED" for e in events)

        print("ALL RUNTIME DEMO CHECKS PASSED")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("FAILED:", exc, file=sys.stderr)
        sys.exit(1)
