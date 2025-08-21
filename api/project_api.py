from ninja import Router, File, Query
from ninja.files import UploadedFile
from typing import List
from .models import Project, ProjectPhoto
from django.db.models import Q
from .schema import (
    ProjectResponse, ProjectListSchema, ErrorResponse, ProjectRequestSchema, ProjectFilter, AddProjectPhoto,
    ProjectStats
)
from core.schema import BaseResponseSchema
from django.core.paginator import Paginator, EmptyPage
from django.template.loader import render_to_string
from django.http import HttpResponse
from weasyprint import HTML
from io import BytesIO
from datetime import datetime

router = Router(tags=["Projects"])


@router.get("/", auth=None, response={200: ProjectListSchema, 400: ErrorResponse})
def list_projects(request, filters: ProjectFilter = Query(...), page: int = 1, page_size: int = 10):
    try:
        queryset = Project.objects.prefetch_related("photos").all().order_by('-created_at')
        if filters.search:
            queryset = queryset.filter(Q(title__icontains=filters.search) | Q(summary__icontains=filters.search) | Q(
                category__icontains=filters.search))
        if filters.category:
            queryset = queryset.filter(category__icontains=filters.category)
        if filters.status:
            queryset = queryset.filter(status__icontains=filters.status)

        paginator = Paginator(queryset, page_size)
        try:
            page_projects = paginator.page(page)
        except EmptyPage:
            return 400, ErrorResponse(message="Invalid page number")
        data = page_projects.object_list

        return 200, ProjectListSchema(
            page=page,
            total=paginator.count,
            page_size=page_size,
            total_pages=paginator.num_pages,
            data=data
        )
    except Exception as e:
        return 400, ErrorResponse(message="Error listing projects", detail=str(e), code=400)


@router.get("/{project_id}", auth=None, response={200: ProjectResponse, 404: ErrorResponse})
def get_project(request, project_id: int):
    try:
        project = Project.objects.prefetch_related("photos").get(id=project_id)
        return 200, ProjectResponse(data=project)
    except Project.DoesNotExist:
        return 404, ErrorResponse(message="Project not found", code=404)


@router.post("/", response={201: ProjectResponse, 400: ErrorResponse})
def create_project(request, payload: ProjectRequestSchema,
                   cover_photo: UploadedFile = File(default=None)):
    try:
        payload_dict = payload.dict()
        if status := payload_dict.get('status'):
            payload_dict['status'] = status.upper()
        project = Project.objects.create(**payload_dict)
        if cover_photo:
            project.cover_image = cover_photo
            project.save()

        return 201, ProjectResponse(data=project)
    except Exception as e:
        return 400, ErrorResponse(message="Error creating project", detail=str(e), code=400)


@router.put("/{project_id}", response={200: ProjectResponse, 404: ErrorResponse, 400: ErrorResponse})
def update_project(request, project_id: int, payload: ProjectRequestSchema,
                   media_files: List[UploadedFile] = File(default=None),
                   cover_photo: UploadedFile = File(default=None)):
    try:
        print(payload)
        project = Project.objects.get(id=project_id)
        payload_dict = payload.dict(exclude={"photos"})
        if status := payload_dict.get('status'):
            payload_dict['status'] = status.upper()
        for attr, value in payload_dict.items():
            setattr(project, attr, value)
        if cover_photo:
            project.cover_image = cover_photo
        project.save()
        if media_files:
            ProjectPhoto.objects.filter(project=project).delete()
            for photo in media_files:
                ProjectPhoto.objects.create(project=project, image=photo)
        return 200, ProjectResponse(data=project)
    except Project.DoesNotExist:
        return 404, ErrorResponse(message="Project not found", code=404)
    except Exception as e:
        return 400, ErrorResponse(message="Error updating project", detail=str(e), code=400)


@router.delete("/{project_id}", response={200: BaseResponseSchema, 404: ErrorResponse})
def delete_project(request, project_id: int):
    try:
        project = Project.objects.get(id=project_id)
        project.delete()
        return {"message": "Project deleted successfully"}
    except Project.DoesNotExist:
        return 404, ErrorResponse(message="Project not found", code=404)


@router.post("/{project_id}/photos", response={201: ProjectResponse, 404: ErrorResponse, 400: ErrorResponse})
def add_project_photos(request, project_id: int, payload: AddProjectPhoto, image: UploadedFile = File(default=None)):
    try:
        project = Project.objects.prefetch_related("photos").get(id=project_id)
        photo = ProjectPhoto.objects.create(
            project=project,
            name=payload.name,
            deliver_date=payload.deliver_date)
        if image:
            photo.image = image
            photo.save()
        return 201, ProjectResponse(data=project)
    except Project.DoesNotExist:
        return 404, ErrorResponse(message="Project not found", code=404)
    except Exception as e:
        return 400, ErrorResponse(message="Error adding photos", detail=str(e), code=400)


@router.delete("/photos/{photo_id}", response={200: BaseResponseSchema, 404: ErrorResponse})
def delete_project_photo(request, photo_id: int):
    try:
        photo = ProjectPhoto.objects.get(id=photo_id)
        photo.delete()
        return 200, BaseResponseSchema(message="Photo deleted successfully")
    except ProjectPhoto.DoesNotExist:
        return 404, ErrorResponse(message="Photo not found", code=404)


@router.get("/{project_id}/download_report", auth=None)
def download_project_report(request, project_id: int):
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return HttpResponse("Not found", status=404)

    # context for template
    generated_at = datetime.now().strftime("%B %d, %Y")
    logo_url = request.build_absolute_uri('/static/images/logo.png')  # adjust path
    cover_url = None
    if project.cover_image:
        cover_url = request.build_absolute_uri(project.cover_image.url)

    context = {
        "project": {
            "title": project.title,
            "summary": project.summary,
            "target_amount": project.target_amount,
            "amount_raised": project.amount_raised,
            "percentage_funded": project.percentage_funded,
            "remaining_amount": project.remaining_amount,
            "deadline": project.deadline,
            "goals": project.goals or [],
            "milestones": project.milestones or [],
            "currency": project.currency,
            "cover_image_url": cover_url,
        },
        "generated_at": generated_at,
        "logo_url": logo_url,
    }

    # render HTML
    html_string = render_to_string("project_report.html", context, request=request)

    # render to PDF
    html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
    pdf_io = BytesIO()
    html.write_pdf(pdf_io)
    pdf_io.seek(0)

    filename = f"NeedsAfrica_Project_Brief_{project.id}.pdf"
    response = HttpResponse(pdf_io.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@router.get("/project_stats/", auth=None,
            response={200: ProjectStats, 400: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def get_stats(request):
    """
    total, active, draft, completed
    """

    qs = Project.objects.all()
    total_ = qs.count()
    completed = qs.filter(status="COMPLETED").count()
    active = qs.filter(status="ACTIVE").count()
    draft = qs.filter(status="DRAFT").count()

    data = {
        "total": total_,
        "completed": completed,
        "active": active,
        "draft": draft
    }
    return 200, ProjectStats(**data)
