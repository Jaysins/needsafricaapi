from ninja import Router, File, Query
from ninja.files import UploadedFile
from ninja.responses import Response

import json
import requests
import os
from typing import List
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from .models import Donation, Project
from .schema import (
    DonationResponse, ErrorResponse, DonationRequestSchema, DonationListResponse, DonationFilter
)
from core.clients import PaypalClient, PaystackClient
from django.core.paginator import Paginator, EmptyPage
from django.utils import timezone
from django.db.models import Sum

router = Router(tags=["Donations"])


@router.post("/donations", auth=None, response={201: dict, 200: dict, 400: ErrorResponse, 404: ErrorResponse})
def create_donation(request, payload: DonationRequestSchema):
    print(payload)
    payload_dict = payload.model_dump()
    payment_client = payload_dict.pop("payment_client")

    callback_url = f"{settings.FRONTEND_URL}"

    if payload.project_id:
        project = Project.objects.get(id=payload.project_id)
        callback_url = f"{settings.FRONTEND_URL}/thankyou"
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
                "currency": payload.currency
            }

            plan_response = paystack.initialize_plan(plan_payload)
            plan_code = plan_response["data"]["plan_code"]

            transaction_payload = {
                "email": payload.donor_email,
                "amount": int(payload.amount * 100),
                "plan": plan_code,
                "callback_url": callback_url,
                "currency": payload.currency
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
                "currency": payload.currency
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
        client = PaypalClient()
        if payload.frequency == "ONCE":
            callback_url = f"{settings.FRONTEND_URL}/thankyou"
            resp = client.create_payment(amount=payload.amount, return_url=callback_url,
                                         description=f"donation: amount:{payload.amount}")
            if resp["success"]:
                donation = Donation.objects.create(**payload_dict)
                donation.reference = resp["payment_id"]
                donation.save()
                data = {
                    "checkout_url": resp["approval_url"]
                }
                return 201, data
            return 400, ErrorResponse(message="An error occured", code="400")
        elif payload.frequency == "MONTHLY":
            resp = client.subcription_payment(amount=payload.amount, return_url=f"{settings.FRONTEND_URL}/thankyou")
            if resp["success"]:
                donation = Donation.objects.create(**payload_dict)
                print(resp["token"])
                donation.reference = resp["token"]
                donation.save()
                data = {
                    "checkout_url": resp["approval_url"]
                }
                return 201, data
            return 400, ErrorResponse(message="An error occured", code="400")
        return 404, ErrorResponse(message="Not yet implemented", code=404)
    else:
        return 404, ErrorResponse(message="Invalid payment method", code=404)


@router.get("/execute_paypal/payment", auth=None,
            response={200: dict, 400: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def execute_payment(request, payer_id: str = None, payment_id: str = None, token: str = None):
    """
        execute paypal payment 
    """
    try:
        client = PaypalClient()
        print(token)
        resp = client.execute_payment_or_subscription(payment_id=payment_id, payer_id=payer_id, token=token)
        if resp["success"]:
            donation = None
            if payer_id and payment_id:
                donation = Donation.objects.filter(reference=payment_id).first()
                if donation and donation.status == donation.DonationStatus.COMPLETED:
                    return 400, ErrorResponse(message="Donation already complete", code=400)
            elif token:
                donation = Donation.objects.filter(reference=token).first()
                if donation and donation.status == donation.DonationStatus.COMPLETED:
                    return 400, ErrorResponse(message="Donation already complete", code=400)
            if donation:
                donation.status = Donation.DonationStatus.COMPLETED
                donation.agreement_id = resp["agreement_id"]
                donation.save()
                if donation.project:
                    donation.project.amount_raised += donation.amount
                    donation.project.update_progress()
                    donation.project.save()
                return 200, {"message": "Payment execute successfully"}
            else:
                return 404, ErrorResponse(message="Donation not found", detail=str(resp), code=404)
        return 400, ErrorResponse(message="AN ERROR OCCURED", code="400")
    except Exception as e:
        return 500, ErrorResponse(message="An error occured", detail=str(e), code=500)


@router.get("/donation/{donation_id}", response={200: DonationResponse, 400: ErrorResponse, 500: ErrorResponse})
def donation(request, donation_id: int):
    """
    donation details
    """

    try:
        donation = Donation.objects.get(id=donation_id)
        return 200, DonationResponse(data=donation)
    except Exception as e:
        return 500, ErrorResponse(message="An error occured while retrieving donation details", detail=str(e))
    except Donation.DoesNotExist:
        return 400, ErrorResponse(message="Donation not found",
                                  detail="The donation with the provided ID does not exist.")


@router.get("/donations", response={200: DonationListResponse})
def list_donations(request, filters: DonationFilter = Query(...), page: int = 1, page_size: int = 10):
    donations_qs = Donation.objects.all().order_by("-created_at")
    if filters.search:
        donations_qs = donations_qs.filter(
            Q(donor_full_name__icontains=filters.search) | Q(donor_email__icontains=filters.search) | Q(
                project__title__icontains=filters.search))

    if filters.frequency:
        donations_qs = donations_qs.filter(frequency__icontains=filters.frequency)
    if filters.status:
        status = filters.status.upper()
        donations_qs = donations_qs.filter(status__icontains=status)

    if filters.payment_method:
        donations_qs = donations_qs.filter(payment_client__icontains=filters.payment_method)

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


@router.post("/paypal/webhook", auth=None)
def paypal_webhook(request):
    payload = request.body.decode("utf-8")
    headers = request.headers

    verification_data = {
        "auth_algo": headers.get("Paypal-Auth-Algo"),
        "cert_url": headers.get("Paypal-Cert-Url"),
        "transmission_id": headers.get("Paypal-Transmission-Id"),
        "transmission_sig": headers.get("Paypal-Transmission-Sig"),
        "transmission_time": headers.get("Paypal-Transmission-Time"),
        "webhook_id": settings.PAYPAL_WEBHOOK_ID,
        "webhook_event": json.loads(payload) if payload else {},
    }

    client = PaypalClient()

    if not client.verify_webhook_signature(verification_data):
        print(f"Webhook verification failed: {verification_data}")
        return Response({}, status=400)

    event = json.loads(payload)
    event_type = event.get("event_type")
    resource = event.get("resource", {})

    if event_type == "PAYMENT.SALE.COMPLETED":
        agreement_id = resource.get("billing_agreement_id")
        amount = resource.get("amount", {}).get("total")
        currency = resource.get("amount", {}).get("currency")

        if agreement_id:
            original_donation = Donation.objects.filter(agreement_id=agreement_id).first()
            if original_donation:
                Donation.objects.create(
                    project=original_donation.project,
                    donor_email=original_donation.donor_email,
                    donor_full_name=original_donation.donor_full_name,
                    amount=amount,
                    currency=currency,
                    frequency=Donation.FrequnceyChoice.MONTHLY,
                    status=Donation.DonationStatus.COMPLETED,
                    # agreement_id=agreement_id,
                    reference=None,
                    payment_plan_code=original_donation.payment_plan_code,
                    payment_client=original_donation.payment_client,
                )
                if original_donation.project:
                    original_donation.project.amount_raised += float(amount)
                    original_donation.project.update_progress()
                    original_donation.project.save()

    return Response({}, status=200)
