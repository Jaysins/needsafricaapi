from .models import ExchangeRate

def conversion(to_currency, from_currency, amount):
    rate = ExchangeRate.objects.last()  

    if not rate:
        raise ValueError("Exchange rate not set in database")

    if from_currency == to_currency:
        return amount

    if from_currency == "USD" and to_currency == "NGN":
        return amount * rate.USD  

    if from_currency == "NGN" and to_currency == "USD":
        return amount * rate.NGN  

    raise ValueError("Unsupported currency conversion")
