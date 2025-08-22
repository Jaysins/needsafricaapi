from ninja import Schema, ModelSchema, FilterSchema
from datetime import date, datetime
from typing import Optional, List, Any, Literal
from core.schema import BaseResponseSchema, ErrorResponse
from .models import (Donation, User, Project, ProjectPhoto, Volunteer, ExchangeRate, Subscription)
from core.clients import PaystackClient


class UserSchema(ModelSchema):
    class Meta:
        model = User
        fields = ["username", "email", "phone_number"]


class LoginSchema(Schema):
    username: str | None = None
    password: str | None = None


class LoginResponse(Schema):
    user: UserSchema
    access_token: str
    refresh_token: str


class RegisterSchema(Schema):
    username: str
    email: str
    password: str


class ProjectPhotoSchema(ModelSchema):
    image: str | None = None

    class Meta:
        model = ProjectPhoto
        fields = ["image", "name", "deliver_date"]


class ProjectSchema(ModelSchema):
    photos: List[ProjectPhotoSchema] | None = None

    class Meta:
        model = Project
        fields = '__all__'


class DonationSchema(ModelSchema):

    class Meta:
        model = Donation
        fields = '__all__'


class DonationRequestSchema(Schema):
    project_id: int | None = None
    donor_email: str | None = None
    frequency: Literal['ONCE', "MONTHLY"] | None = "ONCE"
    payment_client: Literal["PAYSTACK", "PAYPAL"] | None = "PAYSTACK"
    donor_full_name: str | None = None
    amount: float | None = None
    currency: Literal['USD', 'NGN'] | None = None


class DonationFilter(FilterSchema):
    search: str | None = None
    frequency: str | None = None
    status: str | None = None
    payment_method: str | None = None


class DonationResponse(BaseResponseSchema):
    data: DonationSchema | None = None


class DonationListResponse(BaseResponseSchema):
    page: int
    total: int
    page_size: int
    total_pages: int
    data: List[DonationSchema]


class AddProjectPhoto(Schema):
    name: str | None = None
    deliver_date: datetime | None = None


class ProjectRequestSchema(Schema):
    title: str | None = None
    summary: str | None = None
    target_amount: float | None = None
    deadline: datetime | None = None
    milestones: List[str] | None = None
    goals: List[str] | None = None
    donation_supports:List[str] | None = None
    status: str | None = None
    category: str | None = None
    location: str | None = None
    currency: Literal['USD', 'NGN'] | None = None
    receiving_donation: bool | None = None
    donation_reason: str | None = None
    beneficiary_count: int | None = None
    impact_phrase: str | None = None
    impact_count: int | None = None


class ProjectResponse(BaseResponseSchema):
    data: ProjectSchema | None = None


class ProjectListSchema(BaseResponseSchema):
    page: int
    total: int
    page_size: int
    total_pages: int
    data: List[ProjectSchema]


class ProjectFilter(FilterSchema):
    search: str | None = None
    category: str | None = None
    status: str | None = None


class VolunteerRequestSchema(Schema):
    first_name: str
    last_name: str
    age: int
    country: str
    role: str
    availability: str
    hours: Optional[str] = ""
    days: Optional[str] = ""


class VolunteerSchema(ModelSchema):
    class Meta:
        model = Volunteer
        fields = '__all__'


class VolunteerResponse(BaseResponseSchema):
    data: VolunteerSchema | None = None


class VolunteerFilter(FilterSchema):
    search: str | None = None
    country: str | None = None
    role: str | None = None
    availability: str | None = None
    status: bool | None = None  # if you track active/inactive volunteers


class VolunteerListSchema(BaseResponseSchema):
    page: int
    total: int
    page_size: int
    total_pages: int
    data: List[VolunteerSchema]


class ExchangeRateSchema(ModelSchema):
    class Meta:
        model = ExchangeRate
        fields = "__all__"


class ExchangeRatResponse(Schema):
    data: ExchangeRateSchema | None = None


class UpdateExchangeRateRequest(Schema):
    usd_to_ngn_rate: float


class ProjectStats(Schema):
    total: int | None = None
    completed: int | None = None
    active: int | None = None
    draft: int | None = None


class SubscriptionSchema(ModelSchema):
    class Meta:
        model = Subscription
        fields = '__all__'


class SubscriptionListSchema(BaseResponseSchema):
    page: int
    total: int
    page_size: int
    total_pages: int
    data: List[SubscriptionSchema]


class SubscriptionFilter(FilterSchema):
    search: str | None = None
    category: str | None = None
    status: str | None = None


class SubscriptionRequestSchema(Schema):
    email: str


class SubscriptionResponse(BaseResponseSchema):
    data: SubscriptionSchema | None = None
