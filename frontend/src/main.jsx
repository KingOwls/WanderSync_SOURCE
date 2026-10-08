import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { gql } from './api';
import './styles.css';

const money = (n) => new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(n ?? 0);
const emptyAvailability = { outboundDates: [], returnDates: [], combinations: [], airportCodes: [], outboundOfferCount: 0, returnOfferCount: 0 };
const emptyFlightAvailability = { dates: [] };
const emptySourceHealth = { activeCount: 0, totalCount: 4, sources: [] };

function SourceBadge({ item }) {
  const captured = item.scrapedAt ? new Date(item.scrapedAt).toLocaleString('es-CO') : 'sin fecha';
  return <small className="source-badge">Fuente pública: <a href={item.sourceUrl} target="_blank" rel="noreferrer">{item.source}</a> · capturado {captured}</small>;
}

function routeStatusMessage(status) {
  if (status === 'AVAILABLE') return '10 ofertas disponibles';
  if (status === 'PARTIAL') return 'Encontramos menos opciones de lo habitual para esta ruta.';
  if (status === 'SOURCE_UNAVAILABLE') return 'No pudimos comprobar completamente esta ruta porque algunas fuentes no estuvieron disponibles.';
  return 'No encontramos vuelos disponibles actualmente.';
}

function App() {
  const [tab, setTab] = useState('search');
  const [catalogUpdate, setCatalogUpdate] = useState(null);
  const [range, setRange] = useState({ startDate: '', endDate: '' });
  const [flightPage, setFlightPage] = useState({ offset: 0, hasMore: false, totalCount: 0 });
  const checkoutKeys = React.useRef({});
  const [searchMode, setSearchMode] = useState('flights');
  const [network, setNetwork] = useState({ cities: [], routes: [] });
  const [user, setUser] = useState(null);
  const [session, setSession] = useState(null);
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [packages, setPackages] = useState([]);
  const [flightResults, setFlightResults] = useState([]);
  const [connections, setConnections] = useState([]);
  const [flightAvailability, setFlightAvailability] = useState(emptyFlightAvailability);
  const [packageAvailability, setPackageAvailability] = useState(emptyAvailability);
  const [sourceHealth, setSourceHealth] = useState(emptySourceHealth);
  const [resultType, setResultType] = useState('Todos');
  const [airlineFilter, setAirlineFilter] = useState('Todas');
  const [orders, setOrders] = useState([]);
  const [events, setEvents] = useState([]);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [security, setSecurity] = useState(null);
  const [database, setDatabase] = useState(null);
  const [form, setForm] = useState({ origin: '', destination: '', startDate: '', endDate: '' });
  const [auth, setAuth] = useState({ mode: 'login', email: '', fullName: '', password: '' });

  const cityByCode = useMemo(() => Object.fromEntries((network.cities || []).map(city => [city.code, city])), [network.cities]);
  const eligibleRoutes = useMemo(
    () => (network.routes || []).filter(route => route.origin !== route.destination),
    [network.routes, searchMode],
  );
  const originCodes = useMemo(() => [...new Set(eligibleRoutes.map(route => route.origin))], [eligibleRoutes]);
  const destinationRoutes = useMemo(
    () => eligibleRoutes.filter(route => route.origin === form.origin && route.destination !== form.origin),
    [eligibleRoutes, form.origin],
  );
  const selectedRoute = useMemo(
    () => (network.routes || []).find(route => route.origin === form.origin && route.destination === form.destination),
    [network.routes, form.origin, form.destination],
  );

  async function bootstrap() {
    try {
      const data = await gql(`query Bootstrap {
        travelNetwork {
          cities { code name airports }
          routes { origin destination offerCount sources outboundAvailable roundTripAvailable packageAvailable firstDate lastDate lowestPrice coverageStatus visibleOfferCount rawOfferCount sourcesChecked sourcesAvailable }
        }
        catalogUpdate { startedAt finishedAt status intervalHours }
        sessionInfo { authenticated sessionPrefix createdAt rotatedAt userEmail }
        me { id email fullName }
        securityStatus { passwordHashing sessionFixationProtection cookiePolicy loginRateLimit checkoutRateLimit paymentRateLimit dependencyAudit }
        databaseStatus { connected database dbUser users flights hotels cars orders }
      }`);
      setCatalogUpdate(data.catalogUpdate);
      setNetwork(data.travelNetwork || { cities: [], routes: [] });
      setSession(data.sessionInfo); setUser(data.me); setSecurity(data.securityStatus); setDatabase(data.databaseStatus);
    } catch (e) { setNotice(`No se pudo conectar con el Gateway: ${e.message}`); }
  }

  async function refreshSourceHealth() {
    try {
      const data = await gql(`query Health { sourceHealth { activeCount totalCount sources { source status available itemsFound finishedAt } } }`);
      setSourceHealth(data.sourceHealth || emptySourceHealth);
    } catch (_) {
      setSourceHealth(emptySourceHealth);
    }
  }

  useEffect(() => {
    bootstrap(); refreshSourceHealth();
    const timer = setInterval(() => { bootstrap(); refreshSourceHealth(); }, 60000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!eligibleRoutes.length) {
      setForm({ origin: '', destination: '', startDate: '', endDate: '' });
      setPackageAvailability(emptyAvailability); setFlightAvailability(emptyFlightAvailability); setFlightResults([]); setConnections([]); setPackages([]);
      return;
    }
    const origin = originCodes.includes(form.origin) ? form.origin : originCodes[0];
    const destinations = eligibleRoutes.filter(route => route.origin === origin);
    const destination = destinations.some(route => route.destination === form.destination)
      ? form.destination
      : destinations[0]?.destination || '';
    if (origin !== form.origin || destination !== form.destination) {
      setForm({ origin, destination, startDate: '', endDate: '' });
      setFlightResults([]); setConnections([]); setPackages([]);
    }
  }, [eligibleRoutes, originCodes, searchMode, form.origin, form.destination]);

  async function refreshPackageAvailability(origin, destination) {
    if (!origin || !destination || origin === destination) {
      setPackageAvailability(emptyAvailability);
      return;
    }
    try {
      const data = await gql(`query Availability($origin:String!,$destination:String!,$from:String,$to:String){
        travelAvailability(origin:$origin,destination:$destination,outboundLimit:90,returnLimit:90,startDate:$from,endDate:$to){
          origin destination airportCodes outboundDates returnDates outboundOfferCount returnOfferCount
          combinations{ departureDate returnDate nights lowestOutboundPrice lowestReturnPrice lowestFlightTotal }
        }
      }`, { origin, destination, from: range.startDate || null, to: range.endDate || null });
      const next = data.travelAvailability || emptyAvailability;
      setPackageAvailability(next);
      setFlightResults([]); setConnections([]); setPackages([]);
      if (!next.outboundDates?.length) {
        setForm(f => ({ ...f, startDate: '', endDate: '' }));
        setNotice('No hay ofertas activas para esta ruta en el último scraping.');
      } else if (next.combinations?.length) {
        const first = next.combinations[0];
        setForm(f => ({ ...f, startDate: first.departureDate, endDate: first.returnDate }));
        setNotice('');
      } else {
        setForm(f => ({ ...f, startDate: next.outboundDates[0], endDate: '' }));
        if (!next.returnOfferCount) setNotice('Hay vuelos de ida, pero todavía no hay ofertas de regreso.');
        else setNotice('No hay combinación de 1–14 noches entre las fechas publicadas.');
      }
    } catch (e) {
      setPackageAvailability(emptyAvailability);
      setNotice(`No se pudo consultar disponibilidad real: ${e.message}`);
    }
  }

  async function refreshFlightAvailability(origin, destination) {
    if (!origin || !destination || origin === destination) {
      setFlightAvailability(emptyFlightAvailability);
      return;
    }
    try {
      const data = await gql(`query FlightAvailability($origin:String!,$destination:String!,$from:String,$to:String){
        flightAvailability(origin:$origin,destination:$destination,startDate:$from,endDate:$to,limit:90){
          origin destination dates { travelDate directOfferCount connectionCandidateCount }
        }
      }`, { origin, destination, from: range.startDate || null, to: range.endDate || null });
      const next = data.flightAvailability || emptyFlightAvailability;
      setFlightAvailability(next);
      setFlightResults([]); setConnections([]); setPackages([]);
      setForm(f => ({ ...f, startDate: next.dates?.[0]?.travelDate || '', endDate: '' }));
      if (!next.dates?.length) setNotice(routeStatusMessage(selectedRoute?.coverageStatus));
      else setNotice('');
    } catch (e) {
      setFlightAvailability(emptyFlightAvailability);
      setNotice(`No se pudo consultar disponibilidad real de vuelos: ${e.message}`);
    }
  }

  useEffect(() => {
    if (searchMode === 'packages') refreshPackageAvailability(form.origin, form.destination);
    else refreshFlightAvailability(form.origin, form.destination);
  }, [form.origin, form.destination, searchMode, range.startDate, range.endDate]);

  useEffect(() => {
    if (searchMode === 'packages' && selectedRoute && !selectedRoute.packageAvailable) {
      setNotice('Hay vuelos disponibles, pero este destino aún no tiene hotel y auto scrapeados para armar un paquete.');
    }
  }, [searchMode, selectedRoute]);

  const validReturnDates = useMemo(() => {
    if (!form.startDate) return packageAvailability.returnDates || [];
    const start = new Date(`${form.startDate}T12:00:00`);
    return (packageAvailability.returnDates || []).filter(value => {
      const end = new Date(`${value}T12:00:00`);
      const nights = Math.round((end - start) / 86400000);
      return nights >= 1 && nights <= 14;
    });
  }, [packageAvailability.returnDates, form.startDate]);

  const selectedOutboundDate = form.startDate;

  function selectOutbound(value) {
    const start = new Date(`${value}T12:00:00`);
    const nextReturn = (packageAvailability.returnDates || []).find(candidate => {
      const nights = Math.round((new Date(`${candidate}T12:00:00`) - start) / 86400000);
      return nights >= 1 && nights <= 14;
    }) || '';
    setForm(f => ({ ...f, startDate: value, endDate: nextReturn }));
    setFlightResults([]); setPackages([]);
  }

  function selectCombination(combo) {
    setForm(f => ({ ...f, startDate: combo.departureDate, endDate: combo.returnDate }));
    setFlightResults([]); setPackages([]);
  }

  async function searchFlights(e, offset = 0) {
    e?.preventDefault();
    if (!selectedOutboundDate) { setNotice(routeStatusMessage(selectedRoute?.coverageStatus)); return; }
    setLoading(true); setNotice('');
    try {
      const data = await gql(`query Flights($origin:String!,$destination:String!,$travelDate:String!,$offset:Int!){
        flightSearch(origin:$origin,destination:$destination,travelDate:$travelDate,limit:10,offset:$offset){
          origin destination travelDate status availableCount sourcesChecked sourcesAvailable totalCount hasMore offset
          directOffers{ id airline origin destination travelDate departureAt arrivalAt price currency source sourceUrl snapshotId scrapedAt }
          connections{ via stops totalPrice currency warning legs{ id airline origin destination travelDate departureAt arrivalAt price currency source sourceUrl snapshotId scrapedAt } }
        }
      }`, { origin: form.origin, destination: form.destination, travelDate: selectedOutboundDate, offset });
      const result = data.flightSearch || { directOffers: [], connections: [], status: selectedRoute?.coverageStatus };
      setFlightResults(result.directOffers || []);
      setFlightPage({ offset: result.offset || 0, hasMore: result.hasMore || false, totalCount: result.totalCount || 0 });
      setConnections((result.connections || []).slice(0,5));
      setPackages([]);
      if (result.directOffers?.length) setNotice(routeStatusMessage(result.status));
      else if (result.connections?.length) setNotice('No hay ofertas directas para esta fecha. Estas son conexiones sugeridas.');
      else if (result.status === 'SOURCE_UNAVAILABLE') setNotice('No pudimos comprobar completamente esta ruta porque algunas fuentes no estuvieron disponibles.');
      else setNotice('No encontramos vuelos ni conexiones de una escala para esta fecha.');
    } catch (e) { setNotice(e.message); }
    finally { setLoading(false); }
  }

  async function searchPackages(e) {
    e?.preventDefault();
    if (!selectedRoute?.packageAvailable) {
      setNotice('Hay vuelos disponibles, pero este destino aún no tiene hotel y auto scrapeados para armar un paquete.');
      return;
    }
    if (!form.startDate || !form.endDate) {
      setNotice('No hay combinación de 1–14 noches entre las fechas publicadas.');
      return;
    }
    setLoading(true); setNotice('');
    try {
      const data = await gql(`query Search($origin:String!,$destination:String!,$startDate:String!,$endDate:String!){
        travelPackages(origin:$origin,destination:$destination,startDate:$startDate,endDate:$endDate){
          id nights flightTotal total priceBasis warnings
          itinerary { label date origin destination departureAt arrivalAt durationMinutes timeConfirmed }
          outboundFlight{ id airline origin destination travelDate departureAt arrivalAt price currency source sourceUrl scrapedAt }
          returnFlight{ id airline origin destination travelDate departureAt arrivalAt price currency source sourceUrl scrapedAt }
          hotel{ id name roomType city nightlyPrice currency rating source sourceUrl scrapedAt }
          car{ id provider model category dailyPrice currency source sourceUrl scrapedAt }
        }
      }`, form);
      setPackages(data.travelPackages || []); setFlightResults([]);
      if (!data.travelPackages?.length) setNotice('No hay combinación de 1–14 noches entre las fechas publicadas.');
    } catch (e) { setNotice(e.message); }
    finally { setLoading(false); }
  }

  function submitSearch(e) {
    if (searchMode === 'packages') return searchPackages(e);
    return searchFlights(e);
  }

  function switchMode(mode) {
    setSearchMode(mode); setFlightResults([]); setConnections([]); setPackages([]); setNotice('');
  }

  async function submitAuth(e) {
    e.preventDefault(); setLoading(true); setNotice('');
    try {
      if (auth.mode === 'register') {
        await gql(`mutation Register($email:String!,$name:String!,$password:String!){ register(email:$email,fullName:$name,password:$password){ id } }`, { email: auth.email, name: auth.fullName, password: auth.password });
        setNotice('Cuenta creada. Ahora inicia sesión para observar la rotación del identificador de sesión.');
        setAuth(a => ({ ...a, mode: 'login', password: '' }));
      } else {
        const before = session?.sessionPrefix;
        await gql(`mutation Login($email:String!,$password:String!){ login(email:$email,password:$password){ id email fullName } }`, { email: auth.email, password: auth.password });
        await bootstrap();
        setNotice(`Login exitoso. Session Fixation mitigado: la sesión ${before || 'anónima'} fue invalidada y rotada.`);
      }
    } catch (e) { setNotice(`${e.status === 429 ? 'Rate limit activo: ' : ''}${e.message}`); }
    finally { setLoading(false); }
  }

  async function logout() {
    await gql(`mutation { logout }`); setUser(null); setOrders([]); await bootstrap(); setNotice('Sesión cerrada y reemplazada por una sesión anónima nueva.');
  }

  async function checkout(pkg, simulateFailure = null) {
    if (!user) { setTab('account'); setNotice('Inicia sesión antes de reservar.'); return; }
    setLoading(true); setNotice('');
    const requestKey = `checkout:${user.id}:${pkg.id}:${simulateFailure || 'normal'}`;
    const idempotencyKey = checkoutKeys.current[requestKey] ||= sessionStorage.getItem(requestKey) || crypto.randomUUID();
    sessionStorage.setItem(requestKey,idempotencyKey);
    try {
      const data = await gql(`mutation Checkout($outbound:String!,$returnFlight:String!,$hotel:String!,$car:String!,$nights:Int!,$total:Float!,$failure:String,$key:String!){ checkoutPackage(idempotencyKey:$key,outboundFlightId:$outbound,returnFlightId:$returnFlight,hotelId:$hotel,carId:$car,nights:$nights,total:$total,simulateFailure:$failure){ id status paymentStatus failureReason total createdAt } }`, {
        outbound: pkg.outboundFlight.id, returnFlight: pkg.returnFlight.id, hotel: pkg.hotel.id, car: pkg.car.id, nights: pkg.nights, total: pkg.total, failure: simulateFailure, key: idempotencyKey,
      });
      if (["CONFIRMED", "CANCELLED"].includes(data.checkoutPackage.status)) {
        delete checkoutKeys.current[requestKey];
        sessionStorage.removeItem(requestKey);
      }
      setNotice(data.checkoutPackage.status === 'CONFIRMED'
        ? `Reserva local ${data.checkoutPackage.id.slice(0,8)} confirmada. No se ha reservado ni cobrado en proveedores externos.`
        : `Estado ${data.checkoutPackage.status}: ${data.checkoutPackage.failureReason}. Revisa los eventos SAGA.`);
      await loadOrders(); setTab('orders');
    } catch (e) { setNotice(`${e.status === 429 ? 'Rate limit activo: ' : ''}${e.message}`); }
    finally { setLoading(false); }
  }

  async function loadOrders() {
    if (!user) return;
    try { const data = await gql(`query { myBookings { id total status paymentStatus failureReason flightId outboundFlightId returnFlightId hotelId carId createdAt } }`); setOrders(data.myBookings); }
    catch (e) { setNotice(e.message); }
  }
  useEffect(() => { if (tab === 'orders') loadOrders(); }, [tab, user]);

  async function loadEvents(order) {
    setSelectedOrder(order); setEvents([]);
    const data = await gql(`query Events($id:String!){ sagaEvents(orderId:$id){ id step action status detail createdAt } }`, { id: order.id });
    setEvents(data.sagaEvents);
  }

  const airlineOptions = useMemo(() => {
    const names = new Set(flightResults.map(item => item.airline));
    connections.forEach(connection => connection.legs.forEach(leg => names.add(leg.airline)));
    return ['Todas', ...[...names].filter(Boolean).sort()];
  }, [flightResults, connections]);

  const visibleDirectOffers = useMemo(() => {
    if (resultType === 'Conexiones') return [];
    return flightResults
      .filter(item => airlineFilter === 'Todas' || item.airline === airlineFilter)
      .slice()
      .sort((a,b) => Number(a.price) - Number(b.price));
  }, [flightResults, resultType, airlineFilter]);

  const visibleConnections = useMemo(() => {
    if (resultType === 'Directos') return [];
    return connections
      .filter(connection => airlineFilter === 'Todas' || connection.legs.some(leg => leg.airline === airlineFilter))
      .slice()
      .sort((a,b) => Number(a.totalPrice) - Number(b.totalPrice));
  }, [connections, resultType, airlineFilter]);

  const title = useMemo(() => {
    if (tab === 'search') return searchMode === 'flights' ? 'Explora vuelos reales' : 'Arma tu viaje';
    return ({ account: 'Cuenta y sesión', orders: 'Reservas y SAGA', security: 'Seguridad por diseño' })[tab];
  }, [tab, searchMode]);

  const originOptions = originCodes.map(code => cityByCode[code]).filter(Boolean);
  const destinationOptions = destinationRoutes.map(route => cityByCode[route.destination]).filter(Boolean);

  return <div className="app">
    <header>
      <div className="brand"><span className="logo">W</span><div><b>WanderSync</b><small>Travel Solutions</small></div></div>
      <nav>{[['search','Buscar'],['orders','Reservas'],['security','Seguridad'],['account',user ? user.fullName : 'Ingresar']].map(([id,label]) => <button key={id} className={tab===id?'active':''} onClick={()=>setTab(id)}>{label}</button>)}</nav>
    </header>
    <main>
      <section className="hero"><p className="eyebrow">PLATAFORMA TURÍSTICA DISTRIBUIDA</p><h1>{title}</h1><p>Explora cinco ciudades, compara fechas publicadas y construye un viaje con vuelos de ida y vuelta, hotel y vehículo.</p></section>
      <div className="health-banner">Actualización cada {catalogUpdate?.intervalHours || 24} horas · Último ciclo: {catalogUpdate?.startedAt ? new Date(catalogUpdate.startedAt).toLocaleString('es-CO') : 'pendiente'} · {catalogUpdate?.status || 'NOT_RUN'}</div>
      {notice && <div className="notice">{notice}<button onClick={()=>setNotice('')}>×</button></div>}

      {tab==='search' && <>
        <div className="result-filters">
          <label>Consultar desde<input type="date" value={range.startDate} onChange={e=>setRange(r=>({...r,startDate:e.target.value}))}/></label>
          <label>Consultar hasta<input type="date" value={range.endDate} min={range.startDate} onChange={e=>setRange(r=>({...r,endDate:e.target.value}))}/></label>
          <small>El intervalo filtra el catálogo. Selecciona abajo las fechas publicadas.</small>
        </div>
        <div className="mode-switch" role="group" aria-label="Modo de búsqueda">
          <button type="button" className={searchMode==='flights'?'active':''} onClick={()=>switchMode('flights')}>✈ Explorar vuelos</button>
          <button type="button" className={searchMode==='packages'?'active':''} onClick={()=>switchMode('packages')}>🧳 Armar paquete</button>
        </div>
        <form className="search-card compact" onSubmit={submitSearch}>
          <label>Origen<select value={form.origin} onChange={e=>setForm({ ...form, origin:e.target.value, destination:'', startDate:'', endDate:'' })}>{originOptions.map(city=><option key={city.code} value={city.code}>{city.name} ({city.code})</option>)}</select></label>
          <label>Destino<select value={form.destination} onChange={e=>setForm({ ...form, destination:e.target.value, startDate:'', endDate:'' })}>{destinationOptions.map(city=><option key={city.code} value={city.code}>{city.name} ({city.code})</option>)}</select></label>
          <button className="primary" disabled={loading || !form.origin || !form.destination || !form.startDate || (searchMode==='packages' && !form.endDate)}>{loading?'Consultando…':searchMode==='packages'?'Buscar paquetes':'Ver vuelos'}</button>
        </form>

        {searchMode==='flights' ? <section className="availability-panel">
          <div className="availability-head"><div><p className="eyebrow">FECHAS REALES DISPONIBLES</p><h3>Fechas reales disponibles para vuelos</h3></div><small>{routeStatusMessage(selectedRoute?.coverageStatus)}</small></div>
          <div className="date-group"><b>Fecha de viaje</b><div className="date-options">{(flightAvailability.dates || []).map(option => <button type="button" key={option.travelDate} className={`date-chip ${form.startDate===option.travelDate?'selected':''}`} onClick={()=>{setForm(f=>({...f,startDate:option.travelDate,endDate:''}));setFlightResults([]);setConnections([]);}}>{option.travelDate} · {option.directOfferCount} directos · {option.connectionCandidateCount} conexiones</button>)}</div></div>
        </section> : <section className="availability-panel">
          <div className="availability-head"><div><p className="eyebrow">FECHAS REALES DISPONIBLES</p><h3>Fechas reales disponibles del último catálogo</h3></div><small>Aeropuertos encontrados: {(packageAvailability.airportCodes || []).join(', ') || 'sin ofertas'}</small></div>
          <div className="date-group"><b>Salida</b><div className="date-options">{(packageAvailability.outboundDates || []).map(day => <button type="button" key={day} className={`date-chip ${form.startDate===day?'selected':''}`} onClick={()=>selectOutbound(day)}>{day}</button>)}</div></div>
          <div className="date-group"><b>Regreso válido (1–14 noches)</b><div className="date-options">{validReturnDates.map(day => <button type="button" key={day} className={`date-chip ${form.endDate===day?'selected':''}`} onClick={()=>setForm(f=>({...f,endDate:day}))}>{day}</button>)}</div></div>
          {(packageAvailability.combinations || []).length > 0 && <div className="combo-strip">{packageAvailability.combinations.slice(0,12).map(combo => <button type="button" key={`${combo.departureDate}-${combo.returnDate}`} onClick={()=>selectCombination(combo)}><b>{combo.departureDate} → {combo.returnDate}</b><small>{combo.nights} noches · vuelos desde {money(combo.lowestFlightTotal)}</small></button>)}</div>}
        </section>}

        {searchMode==='flights' && <>
          <div className="health-banner"><b>Fuentes activas: {sourceHealth.activeCount} de {sourceHealth.totalCount || 4}</b>{sourceHealth.activeCount < (sourceHealth.totalCount || 4) && <span>Algunas fuentes no estuvieron disponibles durante la última actualización.</span>}</div>
          <div className="result-filters">
            <label>Tipo<select value={resultType} onChange={e=>setResultType(e.target.value)}><option>Todos</option><option>Directos</option><option>Conexiones</option></select></label>
            <label>Aerolínea<select value={airlineFilter} onChange={e=>setAirlineFilter(e.target.value)}>{airlineOptions.map(name=><option key={name}>{name}</option>)}</select></label>
            <span>Orden: <b>Menor precio</b></span>
          </div>
        </>}

        {searchMode==='flights' && <>
          {flightResults.length > 0 && <div className="actions"><button disabled={loading || flightPage.offset === 0} onClick={()=>searchFlights(null, Math.max(0,flightPage.offset-10))}>Anterior</button><span>{flightPage.offset + 1}–{flightPage.offset + flightResults.length} de {flightPage.totalCount} ofertas</span><button disabled={loading || !flightPage.hasMore} onClick={()=>searchFlights(null, flightPage.offset+10)}>Siguiente</button></div>}
          <section className="grid flight-grid">{visibleDirectOffers.map(flight => <article className="flight-card" key={flight.id}>
            <div className="package-top"><span>{flight.origin} → {flight.destination}</span><strong>{money(flight.price)}</strong></div>
            <h3>{flight.airline}</h3>
            <p>{flight.travelDate} · {flight.currency}</p>
            <SourceBadge item={flight}/>
          </article>)}</section>
          {visibleConnections.length > 0 && <section className="connections-section"><h2>Conexiones sugeridas</h2>{visibleConnections.map((connection,index) => <article className="connection-card" key={`${connection.via}-${index}`}>
            <div className="package-top"><span>1 escala · {connection.via}</span><strong>{money(connection.totalPrice)}</strong></div>
            <p>{connection.currency} · {connection.warning || 'Verifica los horarios exactos con las aerolíneas.'}</p>
            <div className="connection-legs">{connection.legs.map(leg => <div className="connection-leg" key={leg.id}><b>{leg.origin} → {leg.destination} · {leg.airline}</b><small>{leg.travelDate} · {money(leg.price)}</small><SourceBadge item={leg}/></div>)}</div>
          </article>)}</section>}
        </>}

        {searchMode==='packages' && <div className="grid">{packages.map(pkg=><article className="package" key={pkg.id}>
          <div className="package-top"><span>{pkg.outboundFlight.origin} ⇄ {pkg.outboundFlight.destination}</span><div className="package-price"><small>Vuelos {money(pkg.flightTotal)}</small><strong>{money(pkg.total)}</strong></div></div>
          <div className="line"><span>✈</span><div><b>Ida · {pkg.outboundFlight.airline}</b><small>{pkg.outboundFlight.travelDate} · {pkg.outboundFlight.origin} → {pkg.outboundFlight.destination} · {money(pkg.outboundFlight.price)}</small><SourceBadge item={pkg.outboundFlight}/></div></div>
          <div className="line"><span>↩</span><div><b>Regreso · {pkg.returnFlight.airline}</b><small>{pkg.returnFlight.travelDate} · {pkg.returnFlight.origin} → {pkg.returnFlight.destination} · {money(pkg.returnFlight.price)}</small><SourceBadge item={pkg.returnFlight}/></div></div>
          <div className="line"><span>⌂</span><div><b>{pkg.hotel.name}{pkg.hotel.roomType ? ` · ${pkg.hotel.roomType}` : ''}</b><small>{pkg.nights} noches · {money(pkg.hotel.nightlyPrice)} / noche{pkg.hotel.rating != null ? ` · ★ ${pkg.hotel.rating}` : ''}</small><SourceBadge item={pkg.hotel}/></div></div>
          <div className="line"><span>🚙</span><div><b>{pkg.car.model}</b><small>{pkg.car.provider}{pkg.car.category ? ` · ${pkg.car.category}` : ''} · {money(pkg.car.dailyPrice)} / día</small><SourceBadge item={pkg.car}/></div></div>
          <div className="timeline itinerary"><h4>Itinerario · {pkg.nights} noches</h4>
            {pkg.itinerary?.map(leg=><div className="event" key={leg.label}><span className="dot"></span><div><b>{leg.label}: {leg.origin} → {leg.destination}</b><small>{leg.date} · {leg.departureAt ? new Date(leg.departureAt).toLocaleString('es-CO') : 'Salida por confirmar'} → {leg.arrivalAt ? new Date(leg.arrivalAt).toLocaleString('es-CO') : 'Llegada por confirmar'}{leg.durationMinutes != null ? ` · ${leg.durationMinutes} minutos` : ''}</small></div></div>)}
            <p>Estancia: {pkg.outboundFlight.travelDate} → {pkg.returnFlight.travelDate} · hotel y vehículo en {cityByCode[form.destination]?.name}</p>
          </div>
          <small>Total estimado para un viajero. Hotel: {money(pkg.hotel.nightlyPrice * pkg.nights)} · vehículo: {money(pkg.car.dailyPrice * pkg.nights)}. No incluye cargos no publicados.</small>
          {pkg.warnings?.map(w=><p className="package-warning" key={w}>{w}</p>)}
          <div className="actions"><button className="primary" disabled={loading} onClick={()=>checkout(pkg)}>Crear reserva local</button><button className="danger" disabled={loading} onClick={()=>checkout(pkg,'return_flight')}>Demo falla regreso</button></div>
        </article>)}</div>}
      </>}

      {tab==='account' && <div className="two-col">
        <section className="panel">
          <h2>{user ? 'Sesión autenticada' : auth.mode==='login' ? 'Iniciar sesión' : 'Crear cuenta'}</h2>
          {user ? <><p><b>{user.fullName}</b><br/>{user.email}</p><button onClick={logout}>Cerrar sesión</button></> : <form className="stack" onSubmit={submitAuth}>
            {auth.mode==='register' && <label>Nombre<input value={auth.fullName} onChange={e=>setAuth({...auth,fullName:e.target.value})} required/></label>}
            <label>Correo<input type="email" value={auth.email} onChange={e=>setAuth({...auth,email:e.target.value})} required/></label>
            <label>Contraseña<input type="password" minLength="8" value={auth.password} onChange={e=>setAuth({...auth,password:e.target.value})} required/></label>
            <button className="primary" disabled={loading}>{auth.mode==='login'?'Entrar':'Registrarme'}</button>
            <button type="button" className="link" onClick={()=>setAuth({...auth,mode:auth.mode==='login'?'register':'login'})}>{auth.mode==='login'?'Crear una cuenta':'Ya tengo cuenta'}</button>
          </form>}
        </section>
        <section className="panel"><h2>Prueba de Session Fixation</h2><div className="metric"><span>Sesión actual</span><b>{session?.sessionPrefix || '...'}</b></div><div className="metric"><span>Estado</span><b>{session?.authenticated?'Autenticada':'Anónima'}</b></div><p className="muted">La cookie es HttpOnly. Al autenticar, el backend elimina el SID anterior y genera uno nuevo.</p></section>
      </div>}

      {tab==='orders' && <div className="two-col wide-left">
        <section className="panel"><h2>Mis reservas</h2>{!user?<p>Inicia sesión para ver reservas.</p>:orders.length===0?<p>No hay reservas todavía.</p>:orders.map(o=><button className={`order ${selectedOrder?.id===o.id?'selected':''}`} key={o.id} onClick={()=>loadEvents(o)}><span><b>{o.id.slice(0,8)}</b><small>{new Date(o.createdAt).toLocaleString()}</small></span><span className={`badge ${o.status.toLowerCase()}`}>{o.status}</span><strong>{money(o.total)}</strong></button>)}</section>
        <section className="panel"><h2>Eventos SAGA</h2>{!selectedOrder?<p>Selecciona una reserva.</p>:<><p>Orden <code>{selectedOrder.id}</code></p><div className="timeline">{events.map(ev=><div className="event" key={ev.id}><span className={`dot ${ev.status.toLowerCase()}`}></span><div><b>{ev.step} · {ev.action}</b><small>{ev.status}{ev.detail?` · ${ev.detail}`:''}</small></div></div>)}</div></>}</section>
      </div>}

      {tab==='security' && <div className="security-grid">
        {database && <section className="panel"><span className="check">✓</span><h3>PostgreSQL conectado</h3><p><b>{database.database}</b> · usuario <code>{database.dbUser}</code></p><p className="muted">Usuarios: {database.users} · Vuelos: {database.flights} · Hoteles: {database.hotels} · Autos: {database.cars} · Órdenes: {database.orders}</p></section>}
        {security && Object.entries({
          'Hash de contraseña': security.passwordHashing,
          'Session Fixation': security.sessionFixationProtection,
          'Cookie': security.cookiePolicy,
          'Rate limit login': security.loginRateLimit,
          'Rate limit checkout': security.checkoutRateLimit,
          'Rate limit pago': security.paymentRateLimit,
          'Supply Chain': security.dependencyAudit,
        }).map(([k,v])=><section className="panel" key={k}><span className="check">✓</span><h3>{k}</h3><p>{v}</p></section>)}
        <section className="panel audit"><h3>Comandos de evidencia</h3><code>./security/audit.sh</code><code>pip-audit -r backend/requirements.txt</code><code>npm audit --prefix frontend</code><p className="muted">Los reportes se guardan en security/reports/.</p></section>
      </div>}
    </main>
    <footer><span>WanderSync · Parcial de Patrones Arquitectónicos Avanzados</span><span>GraphQL Gateway · SAGA · Dask · Prefect · Docker</span></footer>
  </div>;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>);
