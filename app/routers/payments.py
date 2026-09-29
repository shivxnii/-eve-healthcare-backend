import logging
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.models import Booking, BookingStatus, Payment, PaymentStatus, User, WebhookEvent
from app.schemas import MessageResponse, PaymentCreate, PaymentOut, WebhookRequest
from app.tasks import send_booking_confirmation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=PaymentOut, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_payment(
    payload: PaymentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if idempotency_key:
        existing = db.scalar(select(Payment).where(Payment.idempotency_key == idempotency_key))
        if existing:
            if existing.booking_id != payload.booking_id:
                raise HTTPException(status_code=409, detail="Idempotency-Key was already used for another booking")
            return existing

    booking = db.get(Booking, payload.booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You are not authorized to pay for this booking")
    if booking.status != BookingStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Booking cannot be paid in {booking.status.value} state")

    payment = Payment(
        booking_id=booking.id,
        transaction_id=f"txn_{uuid.uuid4().hex[:20]}",
        amount=booking.amount,
        status=payload.simulate,
        idempotency_key=idempotency_key,
    )
    db.add(payment)
    booking.status = BookingStatus.CONFIRMED if payload.simulate == PaymentStatus.SUCCESS else BookingStatus.FAILED
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            existing = db.scalar(select(Payment).where(Payment.idempotency_key == idempotency_key))
            if existing:
                return existing
        raise HTTPException(status_code=409, detail="Payment could not be created due to a concurrent request")
    db.refresh(payment)

    if payload.simulate == PaymentStatus.SUCCESS:
        try:
            send_booking_confirmation.delay(booking.id, current_user.email)
        except Exception:
            logger.info("Celery unavailable; confirmation job skipped for local run")
    return payment


@router.post("/webhook/", response_model=MessageResponse)
@router.post("/webhook", response_model=MessageResponse, include_in_schema=False)
def payment_webhook(payload: WebhookRequest, request: Request, db: Session = Depends(get_db)):
    """Idempotent payment provider webhook.

    provider event_id is unique in the DB. We also store a WebhookEvent row so
    duplicate deliveries are harmless even when the provider retries.
    """
    existing_event = db.scalar(select(WebhookEvent).where(WebhookEvent.event_id == payload.event_id))
    if existing_event and existing_event.processed:
        return MessageResponse(message="Event already processed")
    if existing_event and existing_event.attempts >= settings.webhook_max_retries:
        raise HTTPException(status_code=409, detail="Webhook retry limit reached for this event")

    if not existing_event:
        event = WebhookEvent(event_id=payload.event_id, event_type=payload.event_type, processed=False, attempts=1)
        db.add(event)
        try:
            db.commit()
            db.refresh(event)
        except IntegrityError:
            db.rollback()
            return MessageResponse(message="Event already processed")
    else:
        event = existing_event
        event.attempts += 1
        db.commit()

    try:
        booking = db.get(Booking, payload.booking_id)
        if not booking:
            event.last_error = "Booking not found"
            db.commit()
            raise HTTPException(status_code=404, detail="Booking not found")

        payment = db.scalar(select(Payment).where(Payment.transaction_id == payload.transaction_id))
        if not payment:
            payment = Payment(
                booking_id=booking.id,
                transaction_id=payload.transaction_id,
                amount=booking.amount,
                status=payload.status,
                provider_event_id=payload.event_id,
            )
            db.add(payment)
        else:
            if payment.booking_id != booking.id:
                raise HTTPException(status_code=409, detail="Transaction belongs to another booking")
            payment.status = payload.status
            payment.provider_event_id = payload.event_id

        if payload.status == PaymentStatus.SUCCESS:
            if booking.status == BookingStatus.CANCELLED:
                raise HTTPException(status_code=409, detail="Cancelled booking cannot be confirmed")
            booking.status = BookingStatus.CONFIRMED
        else:
            if booking.status != BookingStatus.CONFIRMED:
                booking.status = BookingStatus.FAILED

        event.processed = True
        event.last_error = None
        db.commit()
        return MessageResponse(message="Webhook processed successfully")
    except HTTPException:
        raise
    except IntegrityError:
        db.rollback()
        return MessageResponse(message="Event already processed")
    except Exception as exc:
        db.rollback()
        logger.exception("Webhook processing failed")
        event = db.scalar(select(WebhookEvent).where(WebhookEvent.event_id == payload.event_id))
        if event:
            event.last_error = str(exc)
            db.commit()
        raise HTTPException(status_code=503, detail="Webhook processing failed; provider may retry")
