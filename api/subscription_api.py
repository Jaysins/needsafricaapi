from django.core.paginator import Paginator, EmptyPage
from django.db.models import Q
from ninja import Router, Query

from core.schema import ErrorResponse
from .models import Subscription

from .schema import SubscriptionResponse, \
    SubscriptionRequestSchema, SubscriptionListSchema,\
    SubscriptionFilter

router = Router(tags=["Subscription"])


@router.post("/", response={201: SubscriptionResponse,
                            400: ErrorResponse}, auth=None)
def create_subscription(
        request,
        payload: SubscriptionRequestSchema,
):
    try:
        # Check for duplicates
        exists = Subscription.objects.filter(
            email=payload.email.strip(),
        ).exists()

        if exists:
            return 400, ErrorResponse(
                message="Subscription already exists", code=400)

        sub = Subscription.objects.create(
            email=payload.email, )

        return 201, SubscriptionResponse(data=sub)

    except Exception as e:
        return 400, ErrorResponse(message="Error creating sub", detail=str(e), code=400)


@router.get("/", response={200: SubscriptionListSchema, 400: ErrorResponse})
def list_subscription(request, filters: SubscriptionFilter = Query(...),
                      page: int = 1, page_size: int = 10):
    try:
        queryset = Subscription.objects.all().order_by(
            '-created_at')
        if filters.search:
            queryset = queryset.filter(Q(email__icontains=filters.search))

        paginator = Paginator(queryset, page_size)
        try:
            page_subscriptions = paginator.page(page)
        except EmptyPage:
            return 400, ErrorResponse(message="Invalid page number")
        data = page_subscriptions.object_list

        return 200, SubscriptionListSchema(
            page=page,
            total=paginator.count,
            page_size=page_size,
            total_pages=paginator.num_pages,
            data=data
        )
    except Exception as e:
        return 400, ErrorResponse(message="Error listing subscriptions",
                                  detail=str(e), code=400)


@router.get("/{subscription_id}", response={200: SubscriptionResponse,
                                       404: ErrorResponse})
def get_subscription(request, subscription_id: int):
    try:
        subscription = Subscription.objects.get(id=subscription_id)
        return 200, SubscriptionResponse(data=subscription)
    except Subscription.DoesNotExist:
        return 404, ErrorResponse(
            message="Subscription not found", code=404)
