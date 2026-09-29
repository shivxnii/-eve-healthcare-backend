import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    from celery import Celery  # type: ignore
except ImportError:  # pragma: no cover
    Celery = None


if Celery:
    celery_app = Celery(
        "eve_healthcare",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
    )
    celery_app.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json")

    @celery_app.task(name="send_booking_confirmation")
    def send_booking_confirmation(booking_id: int, email: str):
        logger.info("Background notification simulated for booking=%s email=%s", booking_id, email)
        return {"booking_id": booking_id, "email": email, "sent": True}
else:
    class _LocalTask:
        @staticmethod
        def delay(booking_id: int, email: str):
            logger.info("Celery unavailable; simulated local background job booking=%s email=%s", booking_id, email)
            return {"booking_id": booking_id, "email": email, "sent": True, "mode": "local"}

    class _LocalCelery:
        pass

    celery_app = _LocalCelery()
    send_booking_confirmation = _LocalTask()
