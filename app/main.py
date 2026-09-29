import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from app.core.rate_limit import RateLimiter

from app.core.config import settings
from app.core.logging import configure_logging
from app.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import CentreTest, DiagnosticCentre, DiagnosticTest, User
from app.routers import auth, bookings, centres, payments

configure_logging()
Base.metadata.create_all(bind=engine)

limiter = RateLimiter(settings.rate_limit)

@asynccontextmanager
async def lifespan(_: FastAPI):
    seed_data()
    yield


def seed_data():
    db = SessionLocal()
    try:
        if db.query(DiagnosticCentre).count() == 0:
            centre = DiagnosticCentre(name="EVE Diagnostics", location="Jaipur")
            tests = [
                DiagnosticTest(name="CBC", description="Complete Blood Count"),
                DiagnosticTest(name="Lipid Profile", description="Cholesterol and lipid panel"),
                DiagnosticTest(name="Thyroid Profile", description="Basic thyroid function panel"),
            ]
            db.add(centre)
            db.add_all(tests)
            db.flush()
            db.add_all([
                CentreTest(centre_id=centre.id, test_id=tests[0].id, price=500),
                CentreTest(centre_id=centre.id, test_id=tests[1].id, price=800),
                CentreTest(centre_id=centre.id, test_id=tests[2].id, price=600),
            ])
        admin = db.scalar(select(User).where(User.email == "admin@evehealthcare.com"))
        if not admin:
            db.add(User(name="EVE Admin", email="admin@evehealthcare.com", password_hash=hash_password("Admin12345!"), is_admin=True))
        db.commit()
    finally:
        db.close()


app = FastAPI(title=settings.app_name, version="1.0.0", description="Diagnostic booking and simulated payment backend", lifespan=lifespan)

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    client_key = request.client.host if request.client else "unknown"
    if not request.url.path in {"/health", "/docs", "/openapi.json", "/redoc"} and not limiter.allowed(client_key):
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"}, headers={"X-Request-ID": request_id})
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    import logging
    logging.getLogger("http").info("request_id=%s method=%s path=%s status=%s duration_ms=%.2f", request_id, request.method, request.url.path, response.status_code, elapsed)
    return response


@app.get("/health", tags=["System"])
def health():
    return {"status": "ok"}


@app.get("/", tags=["System"])
def root():
    return {"service": settings.app_name, "docs": "/docs", "status": "running"}




app.include_router(auth.router)
app.include_router(centres.router)
app.include_router(bookings.router)
app.include_router(payments.router)
