import os
from pathlib import Path

# Use a Windows-compatible local test database path
TEST_DB = Path(__file__).resolve().parent / "eve_healthcare_test.db"

if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["RATE_LIMIT"] = "10000/minute"

from fastapi.testclient import TestClient
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import CentreTest, DiagnosticCentre, DiagnosticTest

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

db = SessionLocal()

centre = DiagnosticCentre(
    name="Test Diagnostics",
    location="Jaipur",
)

test = DiagnosticTest(
    name="CBC",
    description="Complete Blood Count",
)

db.add_all([centre, test])
db.flush()

offering = CentreTest(
    centre_id=centre.id,
    test_id=test.id,
    price=500,
)

db.add(offering)
db.commit()

offering_id = offering.id
db.close()


import pytest


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def offering():
    return offering_id