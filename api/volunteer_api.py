from ninja import Router, File, Form
from ninja.files import UploadedFile

from core.schema import ErrorResponse
from .models import Volunteer

from .schema import VolunteerResponse, VolunteerRequestSchema

router = Router(tags=["Volunteers"])


@router.post("/", response={201: VolunteerResponse, 400: ErrorResponse}, auth=None)
def create_volunteer(
        request,
        payload: VolunteerRequestSchema,
        cv: UploadedFile = File(default=None)
):
    try:
        # Check for duplicates
        exists = Volunteer.objects.filter(
            first_name__iexact=payload.first_name.strip(),
            last_name__iexact=payload.last_name.strip(),
            role__iexact=payload.role.strip()
        ).exists()

        if exists:
            return 400, ErrorResponse(message="Volunteer already exists", code=400)

        volunteer = Volunteer.objects.create(
            first_name=payload.first_name,
            last_name=payload.last_name,
            age=payload.age,
            country=payload.country,
            role=payload.role,
            availability=payload.availability,
            hours=payload.hours,
            days=payload.days,
        )

        if cv:
            volunteer.cv = cv
            volunteer.save()

        return 201, VolunteerResponse(data=volunteer)

    except Exception as e:
        return 400, ErrorResponse(message="Error creating volunteer", detail=str(e), code=400)
