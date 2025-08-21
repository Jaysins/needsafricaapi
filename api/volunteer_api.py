from django.core.paginator import Paginator, EmptyPage
from django.db.models import Q
from ninja import Router, File, Form, Query
from ninja.files import UploadedFile

from core.schema import ErrorResponse
from .models import Volunteer

from .schema import VolunteerResponse, VolunteerRequestSchema, VolunteerListSchema, VolunteerFilter

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


@router.get("/", response={200: VolunteerListSchema, 400: ErrorResponse})
def list_volunteers(request, filters: VolunteerFilter = Query(...),
                    page: int = 1, page_size: int = 10):
    try:
        queryset = Volunteer.objects.all().order_by('-created_at')

        # 🔍 Search across multiple fields
        if filters.search:
            queryset = queryset.filter(
                Q(first_name__icontains=filters.search) |
                Q(last_name__icontains=filters.search) |
                Q(role__icontains=filters.search) |
                Q(country__icontains=filters.search)
            )

        # 🌍 Country filter
        if filters.country:
            queryset = queryset.filter(country__iexact=filters.country.strip())

        # 👔 Role filter
        if filters.role:
            queryset = queryset.filter(role__iexact=filters.role.strip())

        # ⏱ Availability filter
        if filters.availability:
            queryset = queryset.filter(availability__iexact=filters.availability.strip())

        # ✅ Status filter
        if filters.status is not None:
            queryset = queryset.filter(active=filters.status)

        # Pagination
        paginator = Paginator(queryset, page_size)
        try:
            page_volunteers = paginator.page(page)
        except EmptyPage:
            return 400, ErrorResponse(message="Invalid page number")

        data = page_volunteers.object_list

        return 200, VolunteerListSchema(
            page=page,
            total=paginator.count,
            page_size=page_size,
            total_pages=paginator.num_pages,
            data=data
        )
    except Exception as e:
        return 400, ErrorResponse(message="Error listing volunteers", detail=str(e), code=400)


@router.get("/{volunteer_id}", response={200: VolunteerResponse,
                                         404: ErrorResponse})
def get_volunteer(request, volunteer_id: int):
    try:
        volunteer = Volunteer.objects.get(id=volunteer_id)
        return 200, VolunteerResponse(data=volunteer)
    except Volunteer.DoesNotExist:
        return 404, ErrorResponse(
            message="Volunteer not found", code=404)


@router.delete("/{volunteer_id}", response={204: None, 404: ErrorResponse})
def delete_volunteer(request, volunteer_id: int):
    try:
        v = Volunteer.objects.get(id=volunteer_id)
        v.delete()
        return 204, None
    except Volunteer.DoesNotExist:
        return 404, ErrorResponse(message="Volunteer not found", code=404)
