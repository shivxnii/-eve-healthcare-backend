from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.deps import require_admin
from app.cache import clear_prefix, get_json, set_json
from app.database import get_db
from app.models import CentreTest, DiagnosticCentre, DiagnosticTest
from app.schemas import CentreCreate, CentreListItem, CentreOut, CentreUpdate, MessageResponse, OfferingCreate, TestCreate, TestOut, TestUpdate

router = APIRouter(prefix="/centres", tags=["Diagnostic Centres"])


@router.get("", response_model=list[CentreListItem])
def list_centres(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    cache_key = f"centres:{page}:{page_size}"
    cached = get_json(cache_key)
    if cached is not None:
        return cached
    rows = db.scalars(select(DiagnosticCentre).order_by(DiagnosticCentre.id).offset((page - 1) * page_size).limit(page_size)).all()
    result = [CentreListItem(id=x.id, name=x.name, location=x.location).model_dump() for x in rows]
    set_json(cache_key, result, ttl=60)
    return result


@router.get("/catalog/tests", response_model=list[TestOut])
def list_tests(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    rows = db.scalars(select(DiagnosticTest).order_by(DiagnosticTest.id).offset((page - 1) * page_size).limit(page_size)).all()
    return [TestOut(id=t.id, name=t.name, description=t.description, price=0) for t in rows]


@router.get("/catalog/tests/{test_id}", response_model=TestOut)
def get_test(test_id: int, db: Session = Depends(get_db)):
    test = db.get(DiagnosticTest, test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Diagnostic test not found")
    prices = db.scalars(select(CentreTest).where(CentreTest.test_id == test_id)).all()
    price = min((x.price for x in prices), default=0)
    return TestOut(id=test.id, name=test.name, description=test.description, price=price)


@router.get("/{centre_id}", response_model=CentreOut)
def get_centre(centre_id: int, db: Session = Depends(get_db)):
    centre = db.scalar(
        select(DiagnosticCentre)
        .options(joinedload(DiagnosticCentre.offerings).joinedload(CentreTest.test))
        .where(DiagnosticCentre.id == centre_id)
    )
    if not centre:
        raise HTTPException(status_code=404, detail="Diagnostic centre not found")
    tests = [TestOut(id=o.test.id, name=o.test.name, description=o.test.description, price=o.price) for o in centre.offerings]
    return CentreOut(id=centre.id, name=centre.name, location=centre.location, tests=tests)


@router.post("", response_model=CentreListItem, status_code=201)
def create_centre(payload: CentreCreate, _: object = Depends(require_admin), db: Session = Depends(get_db)):
    centre = DiagnosticCentre(name=payload.name.strip(), location=payload.location.strip())
    db.add(centre)
    db.commit()
    db.refresh(centre)
    clear_prefix("centres:")
    return centre


@router.post("/catalog/tests", response_model=TestOut, status_code=201)
def create_test(payload: TestCreate, _: object = Depends(require_admin), db: Session = Depends(get_db)):
    test = DiagnosticTest(name=payload.name.strip(), description=payload.description)
    db.add(test)
    db.commit()
    db.refresh(test)
    return TestOut(id=test.id, name=test.name, description=test.description, price=0)

@router.post("/{centre_id}/tests", response_model=TestOut, status_code=201)
def add_test_to_centre(centre_id: int, payload: OfferingCreate, _: object = Depends(require_admin), db: Session = Depends(get_db)):
    centre = db.get(DiagnosticCentre, centre_id)
    test = db.get(DiagnosticTest, payload.test_id)
    if not centre or not test:
        raise HTTPException(status_code=404, detail="Centre or test not found")
    existing = db.scalar(select(CentreTest).where(CentreTest.centre_id == centre_id, CentreTest.test_id == payload.test_id))
    if existing:
        raise HTTPException(status_code=400, detail="Test is already offered by this centre")
    offering = CentreTest(centre_id=centre_id, test_id=payload.test_id, price=payload.price)
    db.add(offering)
    db.commit()
    db.refresh(offering)
    return TestOut(id=test.id, name=test.name, description=test.description, price=offering.price)



@router.patch("/{centre_id}", response_model=CentreListItem)
def update_centre(centre_id: int, payload: CentreUpdate, _: object = Depends(require_admin), db: Session = Depends(get_db)):
    centre = db.get(DiagnosticCentre, centre_id)
    if not centre:
        raise HTTPException(status_code=404, detail="Diagnostic centre not found")
    if payload.name is not None:
        centre.name = payload.name.strip()
    if payload.location is not None:
        centre.location = payload.location.strip()
    db.commit()
    db.refresh(centre)
    clear_prefix("centres:")
    return centre


@router.delete("/{centre_id}", response_model=MessageResponse, status_code=200)
def delete_centre(centre_id: int, _: object = Depends(require_admin), db: Session = Depends(get_db)):
    centre = db.get(DiagnosticCentre, centre_id)
    if not centre:
        raise HTTPException(status_code=404, detail="Diagnostic centre not found")
    if db.scalar(select(CentreTest).where(CentreTest.centre_id == centre_id)):
        raise HTTPException(status_code=409, detail="Centre has test offerings and cannot be deleted")
    db.delete(centre)
    db.commit()
    clear_prefix("centres:")
    return MessageResponse(message="Diagnostic centre deleted")


@router.patch("/catalog/tests/{test_id}", response_model=TestOut)
def update_test(test_id: int, payload: TestUpdate, _: object = Depends(require_admin), db: Session = Depends(get_db)):
    test = db.get(DiagnosticTest, test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Diagnostic test not found")
    if payload.name is not None:
        test.name = payload.name.strip()
    if payload.description is not None:
        test.description = payload.description
    db.commit()
    db.refresh(test)
    prices = db.scalars(select(CentreTest).where(CentreTest.test_id == test_id)).all()
    price = min((x.price for x in prices), default=0)
    return TestOut(id=test.id, name=test.name, description=test.description, price=price)


@router.delete("/catalog/tests/{test_id}", response_model=MessageResponse)
def delete_test(test_id: int, _: object = Depends(require_admin), db: Session = Depends(get_db)):
    test = db.get(DiagnosticTest, test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Diagnostic test not found")
    if db.scalar(select(CentreTest).where(CentreTest.test_id == test_id)):
        raise HTTPException(status_code=409, detail="Test has centre offerings and cannot be deleted")
    db.delete(test)
    db.commit()
    return MessageResponse(message="Diagnostic test deleted")
