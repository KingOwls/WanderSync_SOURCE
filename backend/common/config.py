import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://wandersync:wandersync_dev_password@localhost:5432/wandersync")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
COOKIE_NAME = os.getenv("COOKIE_NAME", "wander_session")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:8080")
ALLOW_FAILURE_INJECTION = os.getenv("ALLOW_FAILURE_INJECTION", "true").lower() == "true"

FLIGHT_SERVICE_URL = os.getenv("FLIGHT_SERVICE_URL", "http://flight-service:8000")
HOTEL_SERVICE_URL = os.getenv("HOTEL_SERVICE_URL", "http://hotel-service:8000")
CAR_SERVICE_URL = os.getenv("CAR_SERVICE_URL", "http://car-service:8000")
ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order-service:8000")
