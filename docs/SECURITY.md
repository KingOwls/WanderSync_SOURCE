# Ciberseguridad por diseño

## 1. Contraseñas

`backend/common/security.py` usa `argon2-cffi.PasswordHasher`, cuyo algoritmo por defecto es Argon2id en versiones actuales de la librería. `users.password_hash` solo almacena el resultado del hash.

**Evidencia:** registrar usuario y consultar `SELECT email,password_hash FROM users;`.

## 2. Mitigación de Session Fixation

El navegador obtiene primero una sesión anónima al ejecutar `sessionInfo`. Después de validar usuario y contraseña, `login`:

1. lee el SID existente;
2. elimina `session:<SID>` de Redis;
3. genera un SID criptográficamente nuevo con `secrets.token_urlsafe(32)`;
4. almacena la sesión autenticada en Redis;
5. reemplaza la cookie.

La sesión antigua deja de ser válida.

Cookies: `HttpOnly`, `SameSite=Lax`, duración 8 h. En HTTPS debe configurarse `COOKIE_SECURE=true`.

## 3. Rate Limiting

Se implementa contador de ventana fija en Redis mediante `INCR` + `EXPIRE`:

| Operación | Política |
|---|---|
| Register | 5/60 s por IP |
| Login | 5/60 s por IP + correo |
| Checkout | 10/60 s por usuario |
| Payment | 10/60 s por usuario |

Al superar el límite se establece HTTP `429`, `Retry-After` y error GraphQL `RATE_LIMITED`.

## 4. Autorización

- `myBookings` exige sesión autenticada.
- `sagaEvents` verifica que la orden pertenezca al usuario antes de revelar detalles operativos.
- Los microservicios no se publican al host; solo el Gateway tiene puerto de entrada de aplicación.

## 5. Supply Chain Security

- `security/audit.sh` y `security/audit.ps1` ejecutan `pip-audit` para ambos requirements y `npm audit` para frontend.
- Los resultados se escriben en `security/reports/` para adjuntarlos como evidencia formal.

## 6. Recomendaciones de producción

- HTTPS + `COOKIE_SECURE=true`.
- secretos distintos a los valores académicos de `.env.example`.
- `ALLOW_FAILURE_INJECTION=false`.
- rotación de secretos y red privada para PostgreSQL/Redis.
- añadir CSRF tokens si se amplían operaciones state-changing fuera del patrón GraphQL actual y la política SameSite.
