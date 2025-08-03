from ninja import Schema,ModelSchema,FilterSchema
from datetime import date, datetime
from typing import Optional, List, Any,Literal
from core.schema import BaseResponseSchema, ErrorResponse
from .models import (Donation,User,Project,ProjectPhoto)
from core.clients import PaystackClient



class UserSchema(ModelSchema):
    class Meta:
        model = User
        fields = ["username","email","phone_number"]


class LoginSchema(Schema):
    username:str | None = None
    password:str | None = None

class LoginResponse(Schema):
    user: UserSchema
    access_token:str
    refresh_token:str



class RegisterSchema(Schema):
    username:str
    email:str
    password:str

class DonationSchema(ModelSchema):
    class Meta:
        model = Donation
        fields = '__all__'

class DonationRequestSchema(Schema):
    project_id : int | None = None
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


class ProjectPhotoSchema(ModelSchema):
    class Meta:
        model = ProjectPhoto
        fields = ["image"]


class ProjectSchema(ModelSchema):
    photos: List[ProjectPhotoSchema] | None = None
    class Meta:
        model = Project
        fields = '__all__'

class ProjectRequestSchema(Schema):
    title:str | None = None
    summary:str | None = None
    target_amount: float | None = None
    deadline: datetime | None = None
    milestones:str | None = None
    category:  str | None = None
    location: str | None = None
    currency: Literal['USD', 'NGN'] | None = None




class ProjectResponse(BaseResponseSchema):
    data:ProjectSchema | None =None

class ProjectListSchema(BaseResponseSchema):
    page: int
    total: int
    page_size: int
    total_pages: int
    data:List[ProjectSchema]

class ProjectFilter(FilterSchema):
    search:str | None = None
    category:str | None = None
    status:str | None = None


