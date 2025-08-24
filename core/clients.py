from django.conf import settings
from typing import Dict, Any, Optional
from urllib.parse import urlparse, parse_qs
import logging
import requests
import os
import hmac
import hashlib
import datetime
import paypalrestsdk
import os

logger = logging.getLevelName(__name__)


class PaymentError(Exception):
    def __init__(self, message: str, client: str, original_exception: Optional[Exception] = None):
        super().__init__(f"[{client}] {message}")
        self.client = client
        self.original_exception = original_exception


class PaystackClient():
    def __init__(self):
        self.secret_key = settings.PAYSTACK_SECRET_KEY
        self.public_key = settings.PAYSTACK_PUBLIC_KEY
        self.api_url = settings.PAYSTACK_API_URL
        self.client = requests.Session()
        self.client.headers.update({"Content-Type": "application/json",
                                    "Authorization": f"Bearer {self.secret_key}"})
        print(self.secret_key, "secrete key")
        self.headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json'
        }

    def initialize_plan(self, payload: Dict[str, Any]) -> requests.Response:
        url = f"{self.api_url}plan"
        try:
            response = self.client.post(url, json=payload)
            response.raise_for_status()
            print(response.json())
            return response.json()
        except Exception as e:
            print(f"Error initializing payment: {str(e)}")
            raise PaymentError(str(e), "paystack", e)

    def initialize(self, payload: Dict[str, Any]) -> requests.Response:
        url = f"{self.api_url}transaction/initialize"
        try:
            response = self.client.post(url, json=payload)
            print(response.json())
            response.raise_for_status()

            return response.json()
        except requests.exceptions.RequestException as e:
            # logger.error(f"Error initializing payment: {str(e)}")
            print(f"Error initializing payment: {str(e)}")
            raise PaymentError(str(e), "paystack", e)

    def verify_transaction(self, reference: str) -> Dict[str, Any]:
        try:
            res = self.client.get(f"https://api.paystack.co/transaction/verify/{reference}")
            res.raise_for_status()
            logger.info(f"Transaction verified: {res.json()}")
            return res.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error verifying transaction: {e}")
            raise PaymentError(str(e), "paystack", e)

    @staticmethod
    def calculate_hmac(data: bytes, secret: str) -> str:
        return hmac.new(secret.encode("utf-8"), data, digestmod=hashlib.sha512).hexdigest()


class PaypalClient():
    def __init__(self):
        self.secret_key = settings.PAYPAL_SECRET_KEY
        self.client_id = settings.PAYPAL_CLIENT_ID
        self.api_url = settings.PAYPAL_API_URL
        self.headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json'
        }
        print(settings.PAYPAL_API_URL,
              self.client_id, self.secret_key)
        paypalrestsdk.configure({
            "mode": settings.PAYPAL_PAYMENT_MODE,
            "client_id": self.client_id,
            "client_secret": self.secret_key
        })

    def build_url(self, path):
        return f"{self.api_url}{path}"

    def get_access_token(self):
        url = self.build_url("/v1/oauth2/token")
        auth = (self.client_id, self.secret_key)
        data = {'grant_type': 'client_credentials'}
        response = requests.post(url, auth=auth, data=data)
        print(response.text)
        response.raise_for_status()
        return response.json()['access_token']

    def verify_webhook_signature(self, verification_data):
        access_token = self.get_access_token()
        print(self.api_url)
        verify_url = self.build_url("/v1/notifications/verify-webhook-signature")
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        response = requests.post(verify_url, json=verification_data, headers=headers)
        if response.status_code == 200:
            result = response.json()
            return result.get('verification_status') == 'SUCCESS'
        return False

    def create_payment(self, amount, currency="USD", return_url=None, cancel_url=None, description="Deposit to wallet"):
        payment = paypalrestsdk.Payment({
            "intent": "sale",
            "payer": {
                "payment_method": "paypal"
            },
            "redirect_urls": {
                "return_url": return_url or settings.FRONTEND_URL,
                "cancel_url": cancel_url or settings.FRONTEND_URL
            },
            "transactions": [{
                "item_list": {
                    "items": [{
                        "name": "Donation",
                        "sku": "donation",
                        "price": str(amount),
                        "currency": currency,
                        "quantity": 1
                    }]
                },
                "amount": {
                    "total": str(amount),
                    "currency": currency
                },
                "description": description
            }]
        })
        if payment.create():
            approval_url = None
            for link in payment.links:
                if link.rel == "approval_url":
                    approval_url = str(link.href)
                    break
            return {"success": True, "approval_url": approval_url, "payment_id": payment.id}
        else:
            return {"success": False, "error": payment.error}

    def subcription_payment(self, amount, currency="USD", return_url=None, cancel_url=None, name="",
                            description="NeedsAfrica donation"):
        plan = paypalrestsdk.BillingPlan({
            "name": f"Monthly Donation Plan ${amount}",
            "description": f"{description}",
            "type": "INFINITE",
            "payment_definitions": [{
                "name": "Monthly Donation",
                "type": "REGULAR",
                "frequency": "MONTH",
                "frequency_interval": "1",
                "amount": {"currency": "USD", "value": amount},
                "cycles": "0"
            }],
            "merchant_preferences": {
                "auto_bill_amount": "YES",
                "initial_fail_amount_action": "CONTINUE",
                "max_fail_attempts": "1",
                "return_url": return_url or settings.FRONTEND_URL,
                "cancel_url": cancel_url or settings.FRONTEND_URL,
                "setup_fee": {"value": amount, "currency": "USD"}
            }
        })

        if plan.create():
            approval_url = None
            plan.activate()
            future = datetime.datetime.utcnow() + datetime.timedelta(hours=25)
            start_date = future.strftime("%Y-%m-%dT%H:%M:%SZ")
            agreement = paypalrestsdk.BillingAgreement({
                "name": "Monthly Donation Agreement",
                "description": "Agree to donate $100 every month",
                "start_date": start_date,
                "plan": {"id": plan.id},
                "payer": {"payment_method": "paypal"}
            })

            if agreement.create():
                print("Agreement object", agreement)

                # return {"error": "Failed to create agreement", "details": agreement.error}
                for link in agreement.links:
                    if link.rel == "approval_url":
                        approval_url = str(link.href)
                        token = parse_qs(urlparse(approval_url).query).get('token', [None])[0]
                        print("Agreement token:", token)
                        return {"success": True, "approval_url": approval_url, "token": token}

    def execute_payment_or_subscription(self, payment_id, payer_id, token):
        if payer_id:
            payment = paypalrestsdk.Payment.find(payment_id)
            payment = payment.execute({"payer_id": payer_id})
            if payment:
                return {"success": True}
            return {"success": False}
        else:
            payment = paypalrestsdk.BillingAgreement.execute(token)
            print(payment)
            if payment:
                return {"success": True, "agreement_id": payment.id}
            return False
