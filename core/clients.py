from django.conf import settings
from typing import Dict,Any,Optional
import logging
import requests
logger = logging.getLevelName(__name__)
import os
import hmac
import hashlib
import paypalrestsdk


class PaymentError(Exception):
    def __init__(self, message: str, client: str, original_exception: Optional[Exception] = None):
        super().__init__(f"[{client}] {message}")
        self.client = client
        self.original_exception = original_exception


class PaystackClient():
    def __init__(self):
        self.secret_key = os.getenv("PAYSTACK_SECRET_KEY")
        self.public_key = settings.PAYSTACK_PUBLIC_KEY
        self.api_url = settings.PAYSTACK_API_URL
        self.client = requests.Session()
        self.client.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {self.secret_key}"})
        print(self.secret_key, "secrete key")
        self.headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json'
        }

    def initialize_plan(self, payload:Dict[str, Any])-> requests.Response:
        url =f"{self.api_url}plan"
        try:
            response = self.client.post(url, json=payload)
            response.raise_for_status()
            print(response.json())
            return response.json()
        except Exception as e:
            print(f"Error initializing payment: {str(e)}")
            raise PaymentError(str(e), "paystack", e)


    def initialize(self, payload: Dict[str, Any]) -> requests.Response:
        url= f"{self.api_url}transaction/initialize"
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
        paypalrestsdk.configure({
            "mode": "sandbox", 
            "client_id": self.client_id,
            "client_secret": self.secret_key
        })

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
        

    def execute_payment(self, payment_id, payer_id):
        payment = paypalrestsdk.Payment.find(payment_id)
        if payment.execute({"payer_id": payer_id}):
            return {"success": True, "payment_id": payment.id}
        else:
            return {"success": False, "error": payment.error}
