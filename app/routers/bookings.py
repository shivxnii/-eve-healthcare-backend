from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.deps import get_current_user
from app.database import get_db
from app.models import Booking, BookingStatus, CentreTest, User
from app.schemas import BookingCreate, BookingOut, MessageResponse

router = APIRouter(prefix="/bookings", tags=["Bookings"])


def ensure_owner(booking: Booking, user: User):
    if booking.user_id != user.id:
        raise HTTPException(status_code=403, detail="You are not authorized to access this booking")


@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(payload: BookingCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    centre_test = db.get(CentreTest, payload.centre_test_id)
    if not centre_test:
        raise HTTPException(status_code=404, detail="Diagnostic test offering not found")
    if payload.appointment_datetime.tzinfo is not None and payload.appointment_datetime <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Appointment must be in the future")
    booking = Booking(
        user_id=current_user.id,
        centre_test_id=centre_test.id,
        appointment_datetime=payload.appointment_datetime,
        amount=centre_test.price,
        status=BookingStatus.PENDING,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


@router.get("", response_model=list[BookingOut])
def list_bookings(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(Booking)
        .where(Booking.user_id == current_user.id)
        .order_by(Booking.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    ensure_owner(booking, current_user)
    return booking


@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(booking_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    ensure_owner(booking, current_user)
    if booking.status == BookingStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Booking is already cancelled")
    if booking.status == BookingStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail="Confirmed bookings cannot be cancelled in this version")
    if booking.status == BookingStatus.FAILED:
        raise HTTPException(status_code=400, detail="Failed bookings cannot be cancelled")
    booking.status = BookingStatus.CANCELLED
    db.commit()
    db.refresh(booking)
    return booking
