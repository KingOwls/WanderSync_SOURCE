# Red de vuelos multi-ciudad basada en scraping real

WanderSync construye una red turística dinámica a partir de ofertas activas obtenidas por **scraping real**. El frontend no inventa rutas ni fechas: consulta `travelNetwork` y `travelAvailability`, que se derivan del catálogo persistido en PostgreSQL.

## Ciudades iniciales

La red se limita inicialmente a cinco ciudades turísticas:

- **Bogotá (`BOG`)** → aeropuerto `BOG`.
- **Medellín (`MDE`)** → aeropuertos `MDE` y `EOH`; servicios de hotel/auto continúan usando `MDE`.
- **Cali (`CLO`)** → aeropuerto `CLO`.
- **Cartagena (`CTG`)** → aeropuerto `CTG`.
- **Santa Marta (`SMR`)** → aeropuerto `SMR`.

La consolidación `MDE ↔ EOH` sucede solo en lectura. Los vuelos siguen conservando el aeropuerto publicado por la fuente.

## Fuentes de vuelos

- **CLIC** aporta rutas nacionales mediante páginas públicas de ofertas tabulares.
- **SATENA** aporta rutas nacionales y redundancia para varias conexiones de CLIC.
- **LATAM** amplía cobertura, especialmente hacia y desde Santa Marta, y solo persiste ofertas con **fecha exacta** y precio identificable.
- Wingo permanece como adaptador experimental desactivado por defecto.

CLIC, SATENA y LATAM usan adquisición HTTP pública, cache y snapshots. GHL y Alkilautos conservan Playwright porque sus páginas requieren renderizado de navegador.

## Registry no significa disponibilidad

`ingestion/sources/flight_routes.py` contiene URLs auditables mediante `RouteSpec`. Una entrada configurada **no aparece automáticamente** en el producto. Una arista solo se expone cuando PostgreSQL contiene al menos una oferta `active=TRUE` para esa dirección.

Por eso una página existente que hoy no publique ofertas no crea una ruta fantasma.

## `travelNetwork`

El Flight Service agrega únicamente vuelos activos en `/routes`. El Gateway transforma aeropuertos en ciudades turísticas y publica:

```graphql
query {
  travelNetwork {
    cities { code name airports }
    routes {
      origin destination offerCount sources
      outboundAvailable roundTripAvailable packageAvailable
      firstDate lastDate lowestPrice
    }
  }
}
```

`roundTripAvailable` requiere ofertas activas en ambas direcciones.

`packageAvailable` requiere además hotel y auto activos en la ciudad destino. Actualmente Medellín es el principal destino de paquete completo porque GHL y Alkilautos están scrapeados para `MDE`. Una ruta puede ser perfectamente válida en **Explorar vuelos** aunque todavía no pueda armar un paquete.

## Frontend

La interfaz tiene dos modos.

### Explorar vuelos

Muestra toda la red activa. El selector de origen contiene únicamente ciudades con salidas reales. El selector de destino se deriva de las aristas disponibles para ese origen.

Las **fechas se seleccionan exclusivamente de datos scrapeados** mediante chips devueltos por `travelAvailability`. No se permite escribir una fecha arbitraria. Si existe ida pero no regreso, la oferta de ida continúa siendo explorable y se indica que aún no existe combinación ida/vuelta.

### Armar paquete

Solo presenta rutas con `packageAvailable=true`. Una combinación válida usa:

```text
vuelo ida + vuelo regreso + hotel × noches + auto × noches
```

`travelAvailability` entrega hasta 8 fechas de ida, 8 de regreso y hasta 12 combinaciones de 1–14 noches. No rellena huecos con fechas inventadas.

## Resiliencia

Los estados de adquisición permiten demostrar:

- `SUCCESS`: captura externa nueva.
- `CACHED`: reutilización de snapshot reciente.
- `STALE_FALLBACK`: fallo temporal externo y reutilización de un snapshot real previo aceptable.
- `SOURCE_UNAVAILABLE`: no existe una captura real utilizable.

Una ruta fallida dentro de una fuente multi-ruta no debe borrar rutas sanas que no pudieron observarse en esa ejecución.

## Evidencia para la sustentación

1. Ejecutar la ingesta real.
2. Mostrar `scrape_runs` por fuente y estado.
3. Mostrar snapshots HTML/JSON por ruta.
4. Ejecutar `scripts/scraping_study.sql` para obtener:
   - rutas dirigidas activas;
   - cantidad de ofertas y fuentes;
   - precio mínimo/promedio/máximo;
   - primera/última fecha;
   - pares con ida y regreso;
   - destinos con hotel y auto para paquete.
5. Consultar `travelNetwork` y verificar que la interfaz muestra exactamente esa red.
6. Abrir **Explorar vuelos** para una ruta sin paquete y **Armar paquete** para una ruta con `packageAvailable=true`.

WanderSync no realiza reservas en proveedores externos. La SAGA trabaja con **WanderSync Local Hold** sobre ofertas scrapeadas activas para fines académicos.
