"""Public city catalogs. Published starting rates are estimates, not date-specific availability."""
from ingestion.sources.hotels_public import GHLPortonMedellinAdapter
from ingestion.sources.cars_public import NationalMedellinCarsAdapter
from ingestion.models import ScrapeRequest

HOTELS = {
    "BOG": ("ghl_bogota", "https://www.ghlhoteles.com/es/hoteles/colombia/bogota/ghl-collection-93/habitaciones/"),
    "CLO": ("spiwak_cali", "https://www.spiwak.com/es/hoteles/hotel-spiwak-chipichape-en-cali/habitaciones/"),
    "CTG": ("ghl_cartagena", "https://www.ghlhoteles.com/es/hoteles/colombia/cartagena-de-indias/ghl-relax-corales-de-indias/habitaciones/"),
    "SMR": ("ghl_santa_marta", "https://www.ghlhoteles.com/es/hoteles/colombia/santa-marta/ghl-relax-costa-azul/habitaciones/"),
}
CARS = {"BOG": "bogota", "CLO": "cali", "CTG": "cartagena", "SMR": "santa-marta"}

class CityHotelAdapter(GHLPortonMedellinAdapter):
    def __init__(self, city, name, url):
        self.city, self.name, self.url = city, name, url
        if city == "CLO":
            self.allowed_hosts = {"www.spiwak.com", "spiwak.com"}

    def build_requests(self):
        return [ScrapeRequest(self.name, self.kind, self.url, "text=COP", {"city": self.city}, tuple(sorted(self.allowed_hosts)), "http")]

class CityCarAdapter(NationalMedellinCarsAdapter):
    def __init__(self, city, slug):
        self.city, self.name = city, "alkilautos_national_" + slug.replace("-", "_")
        self.url = f"https://alkilautos.com/alquiler-carros-{slug}/ciudad/national/"

    def build_requests(self):
        return [ScrapeRequest(self.name, self.kind, self.url, "text=Precio por día", {"city": self.city}, tuple(sorted(self.allowed_hosts)), "http")]

CITY_ADAPTERS = [CityHotelAdapter(city, *spec) for city, spec in HOTELS.items()] + [CityCarAdapter(city, slug) for city, slug in CARS.items()]
