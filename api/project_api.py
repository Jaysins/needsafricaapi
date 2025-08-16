from ninja import Router, File, Query
from ninja.files import UploadedFile
from typing import List
from .models import Project, ProjectPhoto
from django.db.models import Q
from .schema import (
    ProjectResponse, ProjectListSchema, ErrorResponse, ProjectRequestSchema, ProjectFilter, AddProjectPhoto
)
from core.schema import BaseResponseSchema
from django.core.paginator import Paginator, EmptyPage

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

        project = Project.objects.create(**payload.dict())
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
        for attr, value in payload.dict(exclude={"photos"}).items():
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
        raise e
        # return 400, ErrorResponse(message="Error adding photos", detail=str(e), code=400)


@router.delete("/photos/{photo_id}", response={200: BaseResponseSchema, 404: ErrorResponse})
def delete_project_photo(request, photo_id: int):
    try:
        photo = ProjectPhoto.objects.get(id=photo_id)
        photo.delete()
        return 200, BaseResponseSchema(message="Photo deleted successfully")
    except ProjectPhoto.DoesNotExist:
        return 404, ErrorResponse(message="Photo not found", code=404)

