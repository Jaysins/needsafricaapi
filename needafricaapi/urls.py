from django.contrib import admin
from ninja import NinjaAPI

from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings

from ninja.security import HttpBearer
from rest_framework_simplejwt.authentication import JWTAuthentication as DRFJWTAuth
from api.auth_api import router as auth_api
from api.project_api import router as project_api
from api.donation_api import router as donation_api
from api.volunteer_api import router as volunteer_api
from api.subscription_api import router as subscription_api


class JWTAuth(HttpBearer):
    def authenticate(self, request, token):
        drf_auth = DRFJWTAuth()
        validated = drf_auth.authenticate(request)
        if validated is not None:
            user, _ = validated
            return user


api = NinjaAPI(
    title="NeedAfrica-Api",
    auth=JWTAuth(),
    openapi_extra={
        "info": {"termsOfService": "needsafrica.org"}
    },
    description="NeedAfrica Docs",
)

api.add_router("/auth/", auth_api)
api.add_router("/project/", project_api)
api.add_router("/donation/", donation_api)
api.add_router("/volunteer/", volunteer_api)
api.add_router("/subscription/", subscription_api)

urlpatterns = [
    path('admin/', admin.site.urls),
    path("api/", api.urls),

]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

