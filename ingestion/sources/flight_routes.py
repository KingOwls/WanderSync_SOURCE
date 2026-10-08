from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouteSpec:
    source: str
    origin: str
    destination: str
    url: str
    acquisition_mode: str = "http"

    @property
    def route_key(self) -> str:
        return f"{self.origin}-{self.destination}"


_CLIC = (
    RouteSpec("clicair", "BOG", "EOH", "https://clicair.co/destinos-colombia/es/vuelos-desde-bogota-a-medellin"),
    RouteSpec("clicair", "EOH", "BOG", "https://clicair.co/destinos-colombia/es/vuelos-desde-medellin-a-bogota"),
    RouteSpec("clicair", "BOG", "CLO", "https://clicair.co/destinos-colombia/es/vuelos-desde-bogota-a-cali"),
    RouteSpec("clicair", "CLO", "BOG", "https://clicair.co/destinos-colombia/es/vuelos-desde-cali-a-bogota"),
    RouteSpec("clicair", "EOH", "CLO", "https://clicair.co/destinos-colombia/es/vuelos-desde-medellin-a-cali"),
    RouteSpec("clicair", "CLO", "EOH", "https://clicair.co/destinos-colombia/es/vuelos-desde-cali-a-medellin"),
    RouteSpec("clicair", "EOH", "CTG", "https://clicair.co/destinos-colombia/es/vuelos-desde-medellin-a-cartagena"),
    RouteSpec("clicair", "CTG", "EOH", "https://clicair.co/destinos-colombia/es/vuelos-desde-cartagena-a-medellin"),
    RouteSpec("clicair", "CLO", "CTG", "https://clicair.co/destinos-colombia/es/vuelos-desde-cali-a-cartagena"),
    RouteSpec("clicair", "CTG", "CLO", "https://clicair.co/destinos-colombia/es/vuelos-desde-cartagena-a-cali"),
)

_SATENA = (
    RouteSpec("satena", "BOG", "EOH", "https://rutas-destinos.satena.com/es/vuelos-baratos-desde-bogota-a-medellin"),
    RouteSpec("satena", "EOH", "BOG", "https://rutas-destinos.satena.com/es/vuelos-baratos-desde-medellin-a-bogota"),
    RouteSpec("satena", "BOG", "CLO", "https://rutas-destinos.satena.com/es/vuelos-baratos-desde-bogota-a-cali"),
    RouteSpec("satena", "CLO", "BOG", "https://rutas-destinos.satena.com/es/vuelos-baratos-desde-cali-a-bogota"),
    RouteSpec("satena", "EOH", "CLO", "https://rutas-destinos.satena.com/es/vuelos-baratos-desde-medellin-a-cali"),
    RouteSpec("satena", "CLO", "EOH", "https://rutas-destinos.satena.com/es/vuelos-baratos-desde-cali-a-medellin"),
)

_LATAM = (
    RouteSpec("latam", "BOG", "SMR", "https://www.latamairlines.com/co/es/destinos/vuelos-desde-bogota-a-santa-marta"),
    RouteSpec("latam", "SMR", "BOG", "https://www.latamairlines.com/co/es/destinos/vuelos-desde-santa-marta-a-bogota"),
    RouteSpec("latam", "MDE", "SMR", "https://www.latamairlines.com/co/es/destinos/vuelos-desde-medellin-a-santa-marta"),
    RouteSpec("latam", "SMR", "MDE", "https://www.latamairlines.com/co/es/destinos/vuelos-desde-santa-marta-a-medellin"),
    RouteSpec("latam", "CLO", "SMR", "https://www.latamairlines.com/co/es/destinos/vuelos-desde-cali-a-santa-marta"),
    RouteSpec("latam", "SMR", "CLO", "https://www.latamairlines.com/co/es/destinos/vuelos-desde-santa-marta-a-cali"),
    RouteSpec("latam", "CTG", "SMR", "https://www.latamairlines.com/co/es/destinos/vuelos-desde-cartagena-a-santa-marta"),
)


_JETSMART = (
    RouteSpec("jetsmart", "BOG", "SMR", "https://jetsmart.com/ofertas/es-co/vuelos-desde-bogota-a-santa-marta"),
    RouteSpec("jetsmart", "SMR", "BOG", "https://jetsmart.com/ofertas/es-co/vuelos-desde-santa-marta-a-bogota"),
    RouteSpec("jetsmart", "MDE", "SMR", "https://jetsmart.com/ofertas/es-co/vuelos-desde-medellin-a-santa-marta"),
    RouteSpec("jetsmart", "CLO", "SMR", "https://jetsmart.com/ofertas/es-co/vuelos-desde-cali-a-santa-marta"),
    RouteSpec("jetsmart", "CTG", "BOG", "https://jetsmart.com/ofertas/es-co/vuelos-desde-cartagena-de-indias-a-bogota"),
    RouteSpec("jetsmart", "CTG", "MDE", "https://jetsmart.com/ofertas/es-co/vuelos-desde-cartagena-de-indias-a-medellin"),
    RouteSpec("jetsmart", "CTG", "CLO", "https://jetsmart.com/ofertas/es-co/vuelos-desde-cartagena-de-indias-a-cali"),
    RouteSpec("jetsmart", "MDE", "CTG", "https://jetsmart.com/ofertas/es-co/vuelos-desde-medellin-a-cartagena-de-indias"),
)

_WINGO = (
    RouteSpec("wingo", "BOG", "SMR", "https://www.wingo.com/es/vuelos-de-bogota-a-santa-marta"),
    RouteSpec("wingo", "MDE", "SMR", "https://www.wingo.com/es/vuelos-de-medellin-a-santa-marta"),
    RouteSpec("wingo", "CTG", "BOG", "https://www.wingo.com/es/vuelos-de-cartagena-a-bogota"),
    RouteSpec("wingo", "BOG", "MDE", "https://www.wingo.com/es/vuelos-de-bogota-a-medellin"),
    RouteSpec("wingo", "MDE", "BOG", "https://www.wingo.com/es/vuelos-de-medellin-a-bogota"),
)

def _expand_public_routes(existing, source, template):
    slugs = {"BOG": "bogota", "MDE": "medellin", "CLO": "cali", "CTG": "cartagena-de-indias" if source == "jetsmart" else "cartagena", "SMR": "santa-marta"}
    result = list(existing)
    seen = {(r.origin, r.destination) for r in result}
    for origin, a in slugs.items():
        for destination, b in slugs.items():
            if origin != destination and (origin, destination) not in seen:
                result.append(RouteSpec(source, origin, destination, template.format(a=a, b=b)))
    return tuple(result)

_JETSMART = _expand_public_routes(_JETSMART, "jetsmart", "https://jetsmart.com/ofertas/es-co/vuelos-desde-{a}-a-{b}")
_WINGO = _expand_public_routes(_WINGO, "wingo", "https://www.wingo.com/es/vuelos-de-{a}-a-{b}")

_ROUTE_REGISTRY = {"clicair": _CLIC, "satena": _SATENA, "latam": _LATAM, "jetsmart": _JETSMART, "wingo": _WINGO}


def routes_for_source(source: str) -> tuple[RouteSpec, ...]:
    return _ROUTE_REGISTRY.get(source.strip().lower(), ())
