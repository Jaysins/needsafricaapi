from ninja import Router
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.hashers import make_password

from .schema import *
from .models import User

router = Router()


@router.post("/login", auth=None,
             response={200: LoginResponse, 401: ErrorResponse, 400: ErrorResponse, 500: ErrorResponse})
def login(request, payload: LoginSchema):
    """
    user login
    """
    try:
        if '@' in payload.username:
            user = User.objects.filter(email=payload.username).first()
        else:
            user = User.objects.filter(username=payload.username).first()
        if not user:
            return 400, ErrorResponse(message="User not found", code=400)
        if user.check_password(payload.password):
            refresh = RefreshToken.for_user(user)
            return LoginResponse(user=user, access_token=str(refresh.access_token), refresh_token=str(refresh))
        else:
            return 401, ErrorResponse(message="Incorrect password", code=401)
    except Exception as e:
        return 500, ErrorResponse(message="An error occurred", detail=str(e), code=500)


@router.post("/register", auth=None, response={201: LoginResponse, 400: ErrorResponse, 500: ErrorResponse})
def register(request, payload: RegisterSchema):
    """
    User registration
    """
    try:
        if User.objects.filter(username=payload.username).exists():
            return 400, ErrorResponse(message="Username already taken", code=400)
        if User.objects.filter(email=payload.email).exists():
            return 400, ErrorResponse(message="Email already registered", code=400)

        user = User.objects.create(
            username=payload.username,
            email=payload.email,
            password=make_password(payload.password)
        )

        refresh = RefreshToken.for_user(user)
        return 201, LoginResponse(
            user=user,
            access_token=str(refresh.access_token),
            refresh_token=str(refresh)
        )

    except Exception as e:
        return 500, ErrorResponse(message="An error occurred", detail=str(e), code=500)
