from django.conf import settings


def conversion(to_currency, from_currency, amount):
    from .models import ExchangeRate

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


def retrieve_storage():
    from django.core.files.storage import FileSystemStorage
    if settings.DEBUG:
        return FileSystemStorage(location=settings.MEDIA_ROOT)  # local disk
    from cloudinary_storage.storage import RawMediaCloudinaryStorage
    return RawMediaCloudinaryStorage()
