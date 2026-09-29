from datetime import datetime, timezone
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import BookingStatus, PaymentStatus


class UserSignup(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: EmailStr
    is_active: bool
    is_admin: bool


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TestOut(BaseModel):
    id: int
    name: str
    description: str | None
    price: Decimal


class CentreOut(BaseModel):
    id: int
    name: str
    location: str
    tests: list[TestOut] = Field(default_factory=list)


class CentreCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    location: str = Field(min_length=2, max_length=255)


class CentreUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    location: str | None = Field(default=None, min_length=2, max_length=255)


class TestCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str | None = None


class TestUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None


class OfferingCreate(BaseModel):
    test_id: int = Field(gt=0)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class CentreListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    location: str


class BookingCreate(BaseModel):
    centre_test_id: int = Field(gt=0)
    appointment_datetime: datetime

    @field_validator("appointment_datetime")
    @classmethod
    def future_appointment(cls, value: datetime):
        now = datetime.now(timezone.utc) if value.tzinfo else datetime.now()
        if value <= now:
            raise ValueError("appointment_datetime must be in the future")
        return value


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    centre_test_id: int
    appointment_datetime: datetime
    amount: Decimal
    status: BookingStatus


class PaymentCreate(BaseModel):
    booking_id: int = Field(gt=0)
    simulate: PaymentStatus = PaymentStatus.SUCCESS


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    booking_id: int
    transaction_id: str
    amount: Decimal
    status: PaymentStatus


class WebhookRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=255)
    transaction_id: str = Field(min_length=1, max_length=100)
    booking_id: int = Field(gt=0)
    status: PaymentStatus
    event_type: str = "payment.status.updated"


class MessageResponse(BaseModel):
    message: str
