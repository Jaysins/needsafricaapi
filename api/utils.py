import base64
from django.conf import settings
from django.template.loader import render_to_string

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, \
    FileName, FileType, Disposition

from weasyprint import HTML
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from django.contrib.staticfiles import finders
from django.utils import timezone


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


def currency_symbol_for(code: str) -> str:
    return "$" if code == "USD" else "₦" if code == "NGN" else code


def generate_receipt_pdf_weasy(donation):
    donation_date = donation.payment_completed_at \
                    or donation.created_at or timezone.now()
    ctx = {
        "donor_full_name": donation.donor_full_name,
        "amount": "{:,.2f}".format(donation.amount or 0),
        "currency_symbol": "$" if donation.currency == "USD" else "₦" if donation.currency == "NGN" else donation.currency,
        "reference": donation.reference or "",
        "donation_date": donation_date.strftime("%B %d, %Y"),
        "payment_method": donation.get_payment_client_display() if hasattr(donation,
                                                                           "get_payment_client_display") else donation.payment_client or "",
    }

    html_string = render_to_string("donation_receipt_pdf_template.html", ctx)

    # base_url must resolve {% static %} URLs. Use STATIC_ROOT (after collectstatic)
    # or use the first staticfiles dir: settings.STATICFILES_DIRS[0] if present.
    base_url = getattr(settings, "STATIC_ROOT", None) or (
        settings.STATICFILES_DIRS[0] if getattr(settings, "STATICFILES_DIRS", None) else None)

    html = HTML(string=html_string, base_url=base_url)
    pdf_bytes = html.write_pdf()
    return pdf_bytes


def send_donation_receipt_via_sendgrid(donation):
    """
    Build email HTML, generate PDF receipt, and send via SendGrid SDK.
    Marks donation.receipt_sent True after successful send.
    """
    if not settings.SENDGRID_API_KEY:
        raise RuntimeError("SENDGRID_API_KEY not configured in settings")

    # Prepare context for template
    donation_date = donation.payment_completed_at or donation.created_at or timezone.now()
    ctx = {
        "donor_full_name": donation.donor_full_name,
        "amount": "{:,.2f}".format(donation.amount if donation.amount is not None else 0),
        "currency_symbol": currency_symbol_for(donation.currency),
        "reference": donation.reference or "",
        "donation_date": donation_date.strftime("%B %d, %Y"),
        "payment_method": donation.payment_client or "",
    }

    html_content = render_to_string("donation_receipt.html", ctx)
    subject = "Thank You for Your Generous Donation to NeedsAfrica 💚"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL")
    to_email = donation.donor_email

    message = Mail(from_email=from_email, to_emails=to_email, subject=subject, html_content=html_content)

    # Generate PDF
    pdf_bytes = generate_receipt_pdf_reportlab(donation)
    encoded = base64.b64encode(pdf_bytes).decode()

    attachment = Attachment()
    attachment.file_content = FileContent(encoded)
    attachment.file_type = FileType("application/pdf")
    attachment.file_name = FileName(f"NeedsAfrica_receipt_{donation.reference or donation.pk}.pdf")
    attachment.disposition = Disposition("attachment")

    message.attachment = attachment

    # Send
    sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
    try:
        response = sg.send(message)
        # Consider checking response.status_code to ensure success (202 is success).
        if 200 <= response.status_code < 300:
            # Mark receipt as sent
            donation.receipt_sent = True
            donation.save(update_fields=["receipt_sent"])
        else:
            # raise or log
            raise RuntimeError(f"SendGrid returned status {response.status_code}: {response.body}")
    except Exception as e:
        # Log error here. Use Django logger in production.
        print(f"Failed to send donation receipt: {e}")


def _get_logo_path(static_path="images/logo.png"):
    # finders.find works in dev and after collectstatic (if STATICFILES_DIRS/STATIC_ROOT set)
    return finders.find(static_path)


def generate_receipt_pdf_reportlab(donation):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    left_margin = inch
    top = height - inch

    # Logo
    logo_path = _get_logo_path("images/logo.png")
    # place logo at top-left; adjust size as needed
    c.drawImage(logo_path, left_margin, top - 54, width=120, height=54,
                preserveAspectRatio=True, mask='auto')

    top -= 70

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(left_margin, top, "Donation Receipt")
    top -= 30

    def draw_row(label, value):
        nonlocal top
        c.setFont("Helvetica-Bold", 10)
        c.drawString(left_margin, top, f"{label}:")
        c.setFont("Helvetica", 10)
        c.drawString(left_margin + 140, top, str(value))
        top -= 16

    donation_date = donation.payment_completed_at or donation.created_at or timezone.now()

    # Donation details
    draw_row("Donor Name", donation.donor_full_name)
    draw_row("Donation Amount",
             f"{'$' if donation.currency == 'USD' else '₦' if donation.currency == 'NGN' else donation.currency}{donation.amount:,.2f}")
    draw_row("Transaction ID", donation.reference or "N/A")
    draw_row("Date", donation_date.strftime("%B %d, %Y"))
    draw_row("Payment Method", donation.get_payment_client_display() if hasattr(donation,
                                                                                "get_payment_client_display") else donation.payment_client or "N/A")

    top -= 20

    # Main text content
    text_lines = [
        "Thank you for your generous support. Your gift directly supports NeedsAfrica's mission of delivering",
        "educational and medical equipment to schools, laboratories, and hospitals across Africa.",
        "",
        "NeedsAfrica is a registered nonprofit organization in the State of Texas.",
        "",
        "Please retain this receipt for your records.",
        "",
        "NeedsAfrica Inc. has applied for recognition as a tax-exempt 501(c)(3) organization. If approved, the exemption",
        "will be retroactive to our incorporation date, and your donation will be tax-deductible to the extent allowed by law.",
    ]

    text = c.beginText(left_margin, top)
    text.setFont("Helvetica", 10)
    text.textLines(text_lines)
    c.drawText(text)

    # Footer - positioned relative to content, not fixed at bottom
    footer_y = top - (len(text_lines) * 12) - 40  # Adjust based on text content

    # Center the footer horizontally
    footer_text = "The NeedsAfrica Team"
    footer_contact = "📧 info@needsafrica.org | 🌍 www.needsafrica.org"

    # Calculate center positions
    c.setFont("Helvetica-Bold", 10)
    team_width = c.stringWidth(footer_text, "Helvetica-Bold", 10)
    team_x = (width - team_width) / 2

    c.setFont("Helvetica", 9)
    contact_width = c.stringWidth(footer_contact, "Helvetica", 9)
    contact_x = (width - contact_width) / 2

    # Draw centered footer
    c.setFont("Helvetica-Bold", 10)
    c.drawString(team_x, footer_y, footer_text)

    c.setFont("Helvetica", 9)
    c.drawString(contact_x, footer_y - 14, footer_contact)

    c.showPage()
    c.save()

    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def send_new_volunteer_notification(volunteer):
    """
    Sends an email to admins when a new volunteer registers.
    Uses SendGrid SDK (like donation receipts).
    """
    if not settings.SENDGRID_API_KEY:
        raise RuntimeError("SENDGRID_API_KEY not configured in settings")

    subject = f"New Volunteer Registration: {volunteer.first_name} {volunteer.last_name}"

    ctx = {
        "first_name": volunteer.first_name,
        "last_name": volunteer.last_name,
        "age": volunteer.age,
        "role": volunteer.get_role_display(),
        "availability": volunteer.get_availability_display(),
        "hours": volunteer.hours,
        "days": volunteer.days,
        "email": volunteer.email or "N/A",
        "phone_number": volunteer.phone_number or "N/A",
        "country": volunteer.country,
    }

    # You can make a template "emails/new_volunteer.html"
    html_content = render_to_string("new_volunteer.html", ctx)

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL")
    to_emails = settings.ADMIN_EMAILS

    message = Mail(from_email=from_email, to_emails=to_emails,
                   subject=subject, html_content=html_content)

    # OPTIONAL: attach CV if uploaded
    if volunteer.cv:
        try:
            cv_bytes = volunteer.cv.read()
            encoded = base64.b64encode(cv_bytes).decode()
            attachment = Attachment()
            attachment.file_content = FileContent(encoded)
            attachment.file_type = FileType("application/pdf")
            attachment.file_name = FileName(volunteer.cv.name.split("/")[-1])
            attachment.disposition = Disposition("attachment")
            message.attachment = attachment
        except Exception as e:
            print(f"Could not attach CV: {e}")

    sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
    response = sg.send(message)

    if response.status_code not in range(200, 300):
        raise RuntimeError(f"SendGrid error: {response.status_code}, {response.body}")
