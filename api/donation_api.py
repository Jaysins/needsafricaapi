from ninja import Router, Query
from ninja.responses import Response

import json

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from core.clients import PaypalClient, PaystackClient
from django.core.paginator import Paginator, EmptyPage
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal
import logging

from .models import Donation, Project, ExchangeRate
from .schema import (
    DonationResponse, ErrorResponse, DonationRequestSchema, DonationListResponse, DonationFilter, ExchangeRatResponse,
    UpdateExchangeRateRequest
)

from api.utils import conversion

logger = logging.getLogger(__name__)

router = Router(tags=["Donations"])


def handle_paystack_payment(payload_dict,
                            callback_url):
    """Handle Paystack payment initialization"""
    paystack = PaystackClient()

    try:
        if payload_dict['frequency'] == Donation.FrequencyChoices.MONTHLY:
            # Create subscription plan
            plan_payload = {
                "name": f"Monthly Donation - {payload_dict.get('project_id', 'General')}",
                "interval": "monthly",
                "amount": int(payload_dict['amount'] * 100),
                "currency": payload_dict['currency']
            }

            plan_response = paystack.initialize_plan(plan_payload)
            if not plan_response.get('status'):
                raise Exception("Failed to create payment plan")

            plan_code = plan_response["data"]["plan_code"]

            # Initialize subscription
            transaction_payload = {
                "email": payload_dict['donor_email'],
                "amount": int(payload_dict['amount'] * 100),
                "plan": plan_code,
                "callback_url": callback_url,
                "currency": payload_dict['currency']
            }

            init_response = paystack.initialize(transaction_payload)
            if not init_response.get('status'):
                raise Exception("Failed to initialize payment")

            # Create donation record
            donation_ = Donation.objects.create(**payload_dict)
            donation_.reference = init_response["data"]["reference"]
            donation_.payment_plan_code = plan_code
            donation_.save()

            return 201, {"checkout_url": init_response["data"]["authorization_url"]}

        else:
            # One-time payment
            transaction_payload = {
                "email": payload_dict['donor_email'],
                "amount": int(payload_dict['amount'] * 100),
                "callback_url": callback_url,
                "currency": payload_dict['currency']
            }

            init_response = paystack.initialize(transaction_payload)
            if not init_response.get('status'):
                raise Exception("Failed to initialize payment")

            # Create donation_ record
            donation_ = Donation.objects.create(**payload_dict)
            donation_.reference = init_response["data"]["reference"]
            donation_.save()

            return 201, {"checkout_url": init_response["data"]["authorization_url"]}

    except Exception as e:
        logger.error(f"Paystack payment error: {str(e)}")
        return 400, ErrorResponse(message="Payment initialization failed", code=400)


def handle_paypal_payment(payload_dict,
                          callback_url):
    """Handle PayPal payment initialization"""
    client = PaypalClient()

    try:
        if payload_dict['frequency'] == Donation.FrequencyChoices.ONCE:
            resp = client.create_payment(
                amount=payload_dict['amount'],
                return_url=callback_url,
                description=f"Donation: {payload_dict['amount']} {payload_dict['currency']}"
            )

            if not resp.get("success"):
                raise Exception("Failed to create PayPal payment")

            donation_ = Donation.objects.create(**payload_dict)
            donation_.reference = resp["payment_id"]
            donation_.save()

            return 201, {"checkout_url": resp["approval_url"]}

        elif payload_dict['frequency'] == Donation.FrequencyChoices.MONTHLY:
            resp = client.subcription_payment(
                amount=payload_dict['amount'],
                return_url=callback_url
            )

            if not resp.get("success"):
                raise Exception("Failed to create PayPal subscription")

            donation_ = Donation.objects.create(**payload_dict)
            donation_.reference = resp["token"]
            donation_.save()

            return 201, {"checkout_url": resp["approval_url"]}
        else:
            return 400, ErrorResponse(message="Invalid frequency for PayPal", code=400)

    except Exception as e:
        logger.error(f"PayPal payment error: {str(e)}")
        return 400, ErrorResponse(message="Payment initialization failed", code=400)


@router.post("/donations", auth=None,
             response={201: dict, 400: ErrorResponse,
                       404: ErrorResponse})
def create_donation(request, payload: DonationRequestSchema):
    """Create a new donation with improved validation and currency handling"""

    try:
        with transaction.atomic():
            payload_dict = payload.model_dump()

            # Validate project if specified
            project = None
            if payload.project_id:
                try:
                    project = Project.objects.get(id=payload.project_id)
                    if not project.receiving_donation or project.status != Project.StatusChoices.ACTIVE:
                        return 400, ErrorResponse(
                            message="Project is not accepting donations",
                            code=400
                        )
                except Project.DoesNotExist:
                    return 404, ErrorResponse(message="Project not found", code=404)

            # Validate exchange rate exists if currencies differ
            if project and payload.currency != project.currency:
                if not ExchangeRate.get_current_rate():
                    return 400, ErrorResponse(
                        message="Currency conversion not available at this time",
                        code=400
                    )

            callback_url = f"{settings.FRONTEND_URL}"
            if project:
                callback_url = f"{settings.FRONTEND_URL}/thankyou"

            # Update payload with proper field names
            payload_dict.update({
                'amount': payload_dict.pop('amount'),
                'currency': payload_dict.pop('currency'),
                'project_id': payload.project_id
            })

            # Handle payment processing
            payment_client = payload.payment_client

            if payment_client == Donation.PaymentClientChoices.PAYSTACK:
                return handle_paystack_payment(payload_dict, callback_url)
            elif payment_client == Donation.PaymentClientChoices.PAYPAL:
                return handle_paypal_payment(payload_dict, callback_url)
            else:
                return 400, ErrorResponse(message="Invalid payment method", code=400)

    except Exception as e:
        logger.error(f"Error creating donation: {str(e)}", exc_info=True)
        return 400, ErrorResponse(message="Failed to create donation", code=400)


@router.post("/paystack/webhook", auth=None)
def paystack_webhook(request):
    """Improved Paystack webhook handler"""

    def validate_webhook(request_body, signature):
        """Validate webhook signature"""
        secret = settings.PAYSTACK_SECRET_KEY
        calculated_hash = PaystackClient.calculate_hmac(request_body, secret)
        return calculated_hash == signature

    try:
        with transaction.atomic():
            json_data = json.loads(request.body.decode("utf-8"))
            data = json_data.get("data")

            if not data:
                logger.warning("Paystack webhook: No data in payload")
                return {"status": "error", "message": "No data"}

            # Validate webhook signature
            signature = request.headers.get("X-Paystack-Signature")
            if not validate_webhook(request.body, signature):
                logger.warning("Paystack webhook: Invalid signature")
                return {"status": "error", "message": "Invalid signature"}

            # Check if payment was successful
            if (data.get("status") != "success" or
                    data.get("gateway_response") not in ["Successful", "Approved", "[Test] Approved"]):
                logger.info(f"Paystack webhook: Payment not successful - {data.get('gateway_response')}")
                return {"status": "ignored"}

            # Find donation
            reference = data.get("reference")
            donation = Donation.objects.filter(reference=reference).first()

            if not donation:
                logger.warning(f"Paystack webhook: Donation not found for reference {reference}")
                return {"status": "error", "message": "Donation not found"}

            # Check if already processed
            if donation.status == Donation.StatusChoices.COMPLETED:
                logger.info(f"Paystack webhook: Donation {reference} already completed")
                return {"status": "already_processed"}

            # Process successful payment
            donation.status = Donation.StatusChoices.COMPLETED
            donation.previous_amount_raised = donation.project.amount_raised
            donation.current_amount_raised = donation.project.amount_raised \
                                             + donation.get_project_amount()

            donation.save()  # This will trigger project amount update via model save method

            logger.info(f"Paystack webhook: Successfully processed donation {reference}")
            return {"status": "success"}

    except json.JSONDecodeError:
        logger.error("Paystack webhook: Invalid JSON")
        return {"status": "error", "message": "Invalid JSON"}
    except Exception as e:
        logger.error(f"Paystack webhook error: {str(e)}", exc_info=True)
        return {"status": "error", "message": "Processing failed"}


@router.post("/paypal/webhook", auth=None)
def paypal_webhook(request):
    """Improved PayPal webhook handler"""

    try:
        with transaction.atomic():
            payload = request.body.decode("utf-8")
            headers = request.headers

            # Verify webhook signature
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
                logger.warning("PayPal webhook: Signature verification failed")
                return {"status": "error", "message": "Verification failed"}

            event = json.loads(payload)
            event_type = event.get("event_type")
            resource = event.get("resource", {})

            if event_type == "PAYMENT.SALE.COMPLETED":
                agreement_id = resource.get("billing_agreement_id")
                amount = resource.get("amount", {}).get("total")
                currency = resource.get("amount", {}).get("currency")

                if not agreement_id:
                    logger.warning("PayPal webhook: No agreement_id in payment")
                    return {"status": "ignored"}

                # Find original donation by agreement_id
                original_donation = Donation.objects.filter(agreement_id=agreement_id).first()
                if not original_donation:
                    logger.warning(f"PayPal webhook: No donation found for agreement {agreement_id}")
                    return {"status": "error", "message": "Original donation not found"}

                # Create recurring payment record
                recurring_donation = Donation.objects.create(
                    project=original_donation.project,
                    donor_email=original_donation.donor_email,
                    donor_full_name=original_donation.donor_full_name,
                    amount=Decimal(str(amount)),
                    currency=currency,
                    frequency=Donation.FrequencyChoices.MONTHLY,
                    status=Donation.StatusChoices.COMPLETED,
                    payment_client=original_donation.payment_client,
                    payment_plan_code=original_donation.payment_plan_code,
                    parent_donation=original_donation,
                    reference=f"{agreement_id}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
                )

                logger.info(f"PayPal webhook: Created recurring donation {recurring_donation.id}")
                return {"status": "success"}

            return {"status": "ignored", "message": f"Unhandled event type: {event_type}"}

    except Exception as e:
        logger.error(f"PayPal webhook error: {str(e)}", exc_info=True)
        return {"status": "error", "message": "Processing failed"}


@router.get("/execute_paypal/payment", auth=None, response={200: dict, 400: ErrorResponse, 404: ErrorResponse})
def execute_paypal_payment(request, payer_id: str = None,
                           payment_id: str = None,
                           token: str = None):
    """Execute PayPal payment with improved error handling"""

    try:
        with transaction.atomic():
            client = PaypalClient()

            # Execute payment or subscription
            resp = client.execute_payment_or_subscription(
                payment_id=payment_id,
                payer_id=payer_id,
                token=token
            )

            if not resp.get("success"):
                logger.error(f"PayPal execution failed: {resp}")
                return 400, ErrorResponse(message="Payment execution failed", code=400)

            # Find donation record
            donation = None
            if payment_id:
                donation = Donation.objects.filter(reference=payment_id).first()
            elif token:
                donation = Donation.objects.filter(reference=token).first()

            if not donation:
                logger.error(f"Donation not found for payment_id={payment_id}, token={token}")
                return 404, ErrorResponse(message="Donation not found", code=404)

            # Check if already completed
            if donation.status == Donation.StatusChoices.COMPLETED:
                return 400, ErrorResponse(message="Payment already completed", code=400)

            # Update donation status
            donation.status = Donation.StatusChoices.COMPLETED

            # Set agreement_id for subscriptions
            if token and resp.get("agreement_id"):
                donation.agreement_id = resp["agreement_id"]
            donation.previous_amount_raised = donation.project.amount_raised
            donation.current_amount_raised = donation.project.amount_raised \
                                             + donation.get_project_amount()

            donation.save()  # This will trigger project update

            logger.info(f"PayPal payment executed successfully for donation {donation.id}")
            return 200, {"message": "Payment executed successfully"}

    except Exception as e:
        logger.error(f"PayPal execution error: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="Payment execution failed", code=500)


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
    donations_qs = Donation.objects.all(
    ).order_by("-created_at")
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


@router.get(
    "/exchange_rate",
    auth=None,
    response={200: ExchangeRatResponse, 400: ErrorResponse,
              404: ErrorResponse, 500: ErrorResponse},
)
def exchange_rate(request):
    """Get exchange rate"""

    rate, created = ExchangeRate.objects.get_or_create(
        id=1,
        defaults={"usd_to_ngn_rate": 1600, "ngn_to_usd_rate": 0.000625}
    )

    return 200, ExchangeRatResponse(data=rate)


@router.post(
    "/exchange_rate/update",
    auth=None,
    response={200: ExchangeRatResponse,
              400: ErrorResponse, 500: ErrorResponse},
)
def update_exchange_rate(request, payload: UpdateExchangeRateRequest):
    """Update exchange rate"""

    rate, created = ExchangeRate.objects.get_or_create(
        id=1,
    )

    rate.usd_to_ngn_rate = payload.usd_to_ngn_rate
    rate.ngn_to_usd_rate = 1 / payload.usd_to_ngn_rate
    rate.save()

    return 200, ExchangeRatResponse(data=rate)

# @router.post("/paystack/webhook", auth=None)
# def paystack_webhook(request):
#     def is_valid_hmac(data: dict):
#         headers = request.headers
#         secret = settings.PAYSTACK_SECRET_KEY
#         hash = PaystackClient.calculate_hmac(request.body, secret)
#         if (
#                 hash == headers.get("X-Paystack-Signature")
#                 and data.get("status") == "success"
#                 and data.get("gateway_response") in ["Successful", "Approved", "[Test] Approved"]
#         ):
#             return True
#         return False
#
#     with transaction.atomic():
#         json_data = json.loads(request.body.decode("utf-8"))
#         if not json_data.get("data"):
#             return Response({}, status=400)
#         data = json_data.get("data")
#         donations = Donation.objects.filter(reference=data.get("reference")).first()
#         if donations:
#             donation = donations
#             if is_valid_hmac(data):
#                 print("hmac valid==?")
#                 donation.status = Donation.StatusChoices.COMPLETED
#                 donation.save()
#                 print('in donation.savveee==>', donation.project)
#                 if donation.project:
#                     converted_amount = conversion(donation.project.currency, donation.currency, donation.amount)
#                     donation.project.amount_raised += Decimal(converted_amount).quantize(Decimal("0.01"),
#                                                                                          rounding=ROUND_HALF_UP)
#                     donation.converted_amount = conversion(donation.project.currency, donation.currency,
#                                                            donation.amount)
#                     donation.save()
#                     print("done converting===>", donation.__dict__)
#
#                     donation.project.update_progress()
#                 return Response({}, status=200)
#         return Response({}, status=400)
#


# @router.post("/paypal/webhook", auth=None)
# def paypal_webhook(request):
#     payload = request.body.decode("utf-8")
#     headers = request.headers
#
#     verification_data = {
#         "auth_algo": headers.get("Paypal-Auth-Algo"),
#         "cert_url": headers.get("Paypal-Cert-Url"),
#         "transmission_id": headers.get("Paypal-Transmission-Id"),
#         "transmission_sig": headers.get("Paypal-Transmission-Sig"),
#         "transmission_time": headers.get("Paypal-Transmission-Time"),
#         "webhook_id": settings.PAYPAL_WEBHOOK_ID,
#         "webhook_event": json.loads(payload) if payload else {},
#     }
#
#     client = PaypalClient()
#
#     if not client.verify_webhook_signature(verification_data):
#         print(f"Webhook verification failed: {verification_data}")
#         return Response({}, status=400)
#
#     event = json.loads(payload)
#     event_type = event.get("event_type")
#     resource = event.get("resource", {})
#
#     if event_type == "PAYMENT.SALE.COMPLETED":
#         agreement_id = resource.get("billing_agreement_id")
#         amount = resource.get("amount", {}).get("total")
#         currency = resource.get("amount", {}).get("currency")
#
#         if agreement_id:
#             original_donation = Donation.objects.filter(agreement_id=agreement_id).first()
#             if original_donation:
#                 donation = Donation.objects.create(
#                     project=original_donation.project,
#                     donor_email=original_donation.donor_email,
#                     donor_full_name=original_donation.donor_full_name,
#                     amount=amount,
#                     currency=currency,
#                     frequency=Donation.FrequnceyChoice.MONTHLY,
#                     status=Donation.DonationStatus.COMPLETED,
#                     # agreement_id=agreement_id,
#                     reference=None,
#                     payment_plan_code=original_donation.payment_plan_code,
#                     payment_client=original_donation.payment_client,
#                 )
#                 converted_amount = conversion(to_currency=original_donation.project.currency,
#                                               from_currency=original_donation.currency, amount=original_donation.amount)
#                 donation.converted_amount = converted_amount
#                 donation.save()
#                 if original_donation.project:
#                     converted_amount = conversion(original_donation.project.currency, original_donation.currency,
#                                                   original_donation.amount)
#                     original_donation.project.amount_raised += Decimal(converted_amount).quantize(Decimal("0.01"),
#                                                                                                   rounding=ROUND_HALF_UP)
#                     original_donation.project.update_progress()
#                     original_donation.project.save()
#
#     return Response({}, status=200)
#
# @router.get("/execute_paypal/payment", auth=None,
#             response={200: dict, 400: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
# def execute_payment(request, payer_id: str = None, payment_id: str = None, token: str = None):
#     """
#         execute paypal payment
#     """
#     try:
#         client = PaypalClient()
#         print(token)
#         resp = client.execute_payment_or_subscription(payment_id=payment_id, payer_id=payer_id, token=token)
#         if resp["success"]:
#             donation = None
#             if payer_id and payment_id:
#                 donation = Donation.objects.filter(reference=payment_id).first()
#                 if donation and donation.status == donation.DonationStatus.COMPLETED:
#                     return 400, ErrorResponse(message="Donation already complete", code=400)
#             elif token:
#                 donation = Donation.objects.filter(reference=token).first()
#                 if donation and donation.status == donation.DonationStatus.COMPLETED:
#                     return 400, ErrorResponse(message="Donation already complete", code=400)
#             if donation:
#                 donation.status = Donation.DonationStatus.COMPLETED
#                 if not payer_id and not payment_id:
#                     donation.agreement_id = resp["agreement_id"]
#                 donation.save()
#                 if donation.project:
#                     converted_amount = conversion(to_currency=donation.project.currency,
#                                                   from_currency=donation.currency, amount=donation.amount)
#                     print(converted_amount)
#                     donation.project.amount_raised += Decimal(converted_amount).quantize(Decimal("0.01"),
#                                                                                          rounding=ROUND_HALF_UP)
#                     donation.converted_amount = converted_amount
#                     donation.save()
#                     donation.project.update_progress()
#
#                 return 200, {"message": "Payment execute successfully"}
#             else:
#                 return 404, ErrorResponse(message="Donation not found", detail=str(resp), code=404)
#         return 400, ErrorResponse(message="AN ERROR OCCURED", code="400")
#     except Exception as e:
#         print("the error in execute", str(e))
#         return 500, ErrorResponse(message="An error occured", detail=str(e), code=500)
#
