from ninja import Router,File, Query
from ninja.files import UploadedFile
from ninja.responses import Response

import json
import os
from typing import List
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from .models import Donation, Project
from .schema import (
    DonationSchema, DonationResponse, ErrorResponse, DonationRequestSchema, DonationListResponse, DonationFilter
)
from core.schema import BaseResponseSchema
from core.pagination import paginated_results
from core.clients import PaypalClient, PaystackClient
from django.core.paginator import Paginator, EmptyPage
from django.utils import timezone
from django.db.models import Sum


router = Router(tags=["Donations"])



@router.post("/donations", auth=None, response={201: dict, 400: ErrorResponse, 404: ErrorResponse})
def create_donation(request, payload: DonationRequestSchema):
    print(payload)
    payload_dict = payload.model_dump() 
    payment_client = payload_dict.pop("payment_client")

    callback_url = f"{settings.FRONTEND_URL}"

    if payload.project_id:
        project = Project.objects.get(id=payload.project_id)
        callback_url=f"{settings.FRONTEND_URL}/projects/{project.id}"
        if not project:
            return 404, ErrorResponse(message="Project not found", code=404)

    
    if payment_client == 'PAYSTACK':
        paystack = PaystackClient()

        if payload.frequency == "MONTHLY":
            # plan
            plan_payload = {
                "name": f"Monthly Donation Plan - {payload.project_id}",
                "interval": "monthly",
                "amount": int(payload.amount * 100),
                "currency":payload.currency
            }

            plan_response = paystack.initialize_plan(plan_payload)
            plan_code = plan_response["data"]["plan_code"]

            transaction_payload = {
                "email": payload.donor_email,
                "amount": int(payload.amount * 100),  
                "plan": plan_code,
                "callback_url": callback_url,
                "currency":payload.currency
            }

            init_response = paystack.initialize(transaction_payload)
            authorization_url = init_response["data"]["authorization_url"]

            ref = init_response.get("data").get("reference")

           
            data = {
                "checkout_url": authorization_url
            }

            donation = Donation.objects.create(**payload_dict)
            donation.reference = ref
            donation.payment_plan_code = plan_code
            donation.save()

            return 201, data

        else:
            transaction_payload = {
                "email": payload.donor_email,
                "amount": int(payload.amount * 100),
                "callback_url": f"{settings.FRONTEND_URL}/thankyou",
                "currency":payload.currency
            }

            init_response = paystack.initialize(transaction_payload)
            authorization_url = init_response["data"]["authorization_url"]
            ref = init_response.get("data").get("reference")

            data = {
                "checkout_url": authorization_url
            }
            donation = Donation.objects.create(**payload_dict)
            donation.reference = ref
            donation.save()
            

            return 201, data
        
    if payment_client == "PAYPAL":
        return 404, ErrorResponse(message="Not yet implemented", code=404)    
    else:
        return 404, ErrorResponse(message="Invalid payment method", code=404)   

@router.get("/donation/{donation_id}", response={200:DonationResponse, 400:ErrorResponse, 500:ErrorResponse})
def donation(request,donation_id:int):
    """
    donation details
    """

    try:
        donation = Donation.objects.get(id=donation_id)
        return 200,DonationResponse(data=donation)
    except Exception as e:
        return 500, ErrorResponse(message="An error occured while retrieving donation details", detail=str(e))
    except Donation.DoesNotExist:
        return 400, ErrorResponse(message="Donation not found", detail="The donation with the provided ID does not exist.")


@router.get("/donations", response={200: DonationListResponse})
def list_donations(request, filters: DonationFilter = Query(...), page:int =1, page_size:int=10):
    
    
    donations_qs = Donation.objects.all().order_by("-created_at")
    if filters.search:
        donations_qs = donations_qs.filter(Q(donor_full_name__icontains=filters.search)| Q(donor_email__icontains=filters.search) | Q(project__title__icontains=filters.search))

    if filters.frequency:
        donations_qs= donations_qs.filter(frequency=filters.frequency)
    if filters.status:
        status = filters.status.upper()
        donations_qs = donations_qs.filter(status=status)

    if filters.payment_method:
        donations_qs = donations_qs.filter(payment_client=filters.payment_method)

    paginator = Paginator(donations_qs, page_size)
    total = paginator.count
    total_pages = paginator.num_pages
    try:
        donations = paginator.page(page)
    except EmptyPage:
        donations = []
    data = list(donations) if donations else []
    return 200, DonationListResponse(
        data=data,
        page=page,
        total=total,
        page_size=page_size,
        total_pages=total_pages
    )


@router.post("/paystack/webhook", auth=None)
def paystack_webhook(request):
    def is_valid_hmac(data: dict):
        headers = request.headers
        secret = os.environ.get("PAYSTACK_SECRET_KEY", "")
        hash = PaystackClient.calculate_hmac(request.body, secret)
        if (
            hash == headers.get("X-Paystack-Signature")
            and data.get("status") == "success"
            and data.get("gateway_response") in ["Successful", "Approved", "[Test] Approved"]
        ):
            return True
        return False

    with transaction.atomic():
        json_data = json.loads(request.body.decode("utf-8"))
        if not json_data.get("data"):
            return Response({}, status=400)
        data = json_data.get("data")
        donations = Donation.objects.filter(reference=data.get("reference")).first()
        if donations:
            donation = donations
            if is_valid_hmac(data):
                donation.status = Donation.DonationStatus.COMPLETED
                donation.save()
                if donation.project:
                    donation.project.amount_raised += donation.amount
                    donation.project.update_progress()
                return Response({}, status=200)
        return Response({}, status=400)


@router.get("/donation_metric", response={200: dict})
def donation_metric(request):
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timezone.timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    total_donations = Donation.objects.count()
    total_amount = Donation.objects.aggregate(total=Sum("amount"))['total'] or 0
    today_amount = Donation.objects.filter(created_at__gte=today_start).aggregate(total=Sum("amount"))['total'] or 0
    week_amount = Donation.objects.filter(created_at__gte=week_start).aggregate(total=Sum("amount"))['total'] or 0
    month_amount = Donation.objects.filter(created_at__gte=month_start).aggregate(total=Sum("amount"))['total'] or 0

    return 200, {
        "total_donations": total_donations,
        "total_amount": total_amount,
        "today_amount": today_amount,
        "week_amount": week_amount,
        "month_amount": month_amount
    }