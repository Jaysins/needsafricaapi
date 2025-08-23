from django.db import models
from core.models import BaseDBModel
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from django.contrib.auth.models import AbstractUser


class User(AbstractUser, BaseDBModel):
    username = models.CharField(max_length=140, blank=True, null=True,
                                unique=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return self.username


class ExchangeRate(BaseDBModel):
    """
    Simplified exchange rate model with proper admin controls.
    Stores the rate for converting 1 USD to NGN.
    """
    usd_to_ngn_rate = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=1,
        help_text="How many NGN equals 1 USD (e.g., 1600.0000)"
    )
    ngn_to_usd_rate = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=1,
        help_text="How many USD equals 1 NGN (e.g., 0.000625)"
    )
    effective_date = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-effective_date']
        verbose_name = "Exchange Rate"
        verbose_name_plural = "Exchange Rates"

    def save(self, *args, **kwargs):
        if self.is_active:
            # Deactivate all other rates when setting a new active rate
            ExchangeRate.objects.filter(is_active=True).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_current_rate(cls):
        """Get the current active exchange rate"""
        return cls.objects.filter(is_active=True).first()

    @classmethod
    def convert_currency(cls, amount, from_currency, to_currency):
        """
        Convert amount between USD and NGN
        Returns Decimal with proper precision
        """
        if from_currency == to_currency:
            return Decimal(str(amount))

        current_rate = cls.get_current_rate()
        if not current_rate:
            raise ValueError("No active exchange rate found")

        amount_decimal = Decimal(str(amount))

        if from_currency == 'USD' and to_currency == 'NGN':
            converted = amount_decimal * current_rate.usd_to_ngn_rate
        elif from_currency == 'NGN' and to_currency == 'USD':
            converted = amount_decimal / current_rate.usd_to_ngn_rate
        else:
            raise ValueError(f"Unsupported currency conversion: {from_currency} to {to_currency}")

        return converted.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def __str__(self):
        return f"1 USD = {self.usd_to_ngn_rate} NGN (Active: {self.is_active})"


class Project(BaseDBModel):
    """Updated project model with better donation handling"""

    class CurrencyChoices(models.TextChoices):
        USD = 'USD', 'USD'
        NGN = 'NGN', 'NGN'

    class StatusChoices(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        ACTIVE = 'ACTIVE', 'Active'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        PAUSED = 'PAUSED', 'Paused'

    class CategoryChoices(models.TextChoices):
        EDUCATION = 'education', 'Education'
        COMMUNITY = 'community', 'Community Development'
        HEALTHCARE = 'healthcare', 'Healthcare'
        ENVIRONMENT = 'environment', 'Environment'
        EMERGENCY = 'emergency', 'Emergency Relief'

    # Basic project info
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    # Financial targets
    target_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(
        max_length=3,
        choices=CurrencyChoices.choices,
        default=CurrencyChoices.USD
    )
    amount_raised = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Calculated fields
    percentage_funded = models.FloatField(default=0.0)
    remaining_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Project details
    category = models.CharField(max_length=20, choices=CategoryChoices.choices,
                                null=True)
    location = models.CharField(max_length=150, blank=True, null=True)
    deadline = models.DateField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.DRAFT
    )

    # Settings
    donation_reason = models.CharField(max_length=150, blank=True, null=True)
    receiving_donation = models.BooleanField(default=True)

    # Rich content
    cover_image = models.ImageField(upload_to='project_covers/', blank=True, null=True)
    milestones = models.JSONField(default=list, blank=True)
    goals = models.JSONField(default=list, blank=True)
    donation_supports = models.JSONField(default=list, blank= True, null=True)

    # Impact tracking
    beneficiary_count = models.IntegerField(default=0, null=True, blank=True)
    impact_count = models.IntegerField(default=0, null=True, blank=True)
    impact_phrase = models.CharField(max_length=150, blank=True, null=True)

    def add_donation_amount(self, amount):
        """Add donation amount and update progress"""
        self.amount_raised += Decimal(str(amount))
        self.update_progress()

    def update_progress(self):
        """Update funding progress calculations"""
        print("updating progress===>>>>>")
        if self.target_amount > 0:
            self.percentage_funded = float((self.amount_raised / self.target_amount) * 100)
            self.remaining_amount = max(self.target_amount - self.amount_raised, Decimal('0.00'))

            # Auto-complete if target reached
            if (self.amount_raised >= self.target_amount and
                    self.status == self.StatusChoices.ACTIVE):
                self.status = self.StatusChoices.COMPLETED
        else:
            self.percentage_funded = 0.0
            self.remaining_amount = Decimal('0.00')

        # Always save after updating progress
        self.save()

    def get_donations_summary(self):
        """Get summary of donations for this project"""
        from django.db.models import Sum, Count

        completed_donations = self.donations.filter(status=Donation.StatusChoices.COMPLETED)

        return {
            'total_donors': completed_donations.values('donor_email').distinct().count(),
            'total_donations': completed_donations.count(),
            'amount_raised': self.amount_raised,
            'average_donation': completed_donations.aggregate(
                avg=models.Avg('project_currency_amount')
            )['avg'] or 0,
            'recurring_donors': completed_donations.filter(
                frequency=Donation.FrequencyChoices.MONTHLY
            ).values('donor_email').distinct().count(),
        }

    def __str__(self):
        return f"{self.title} - {self.percentage_funded:.1f}% funded ({self.get_status_display()})"


# proof of delivery
class ProjectPhoto(BaseDBModel):
    name = models.CharField(max_length=150, blank=True, null=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='project_photos/')
    deliver_date = models.DateField(blank=True, null=True)

    def __str__(self):
        return f"Photo for {self.project.title}"


class Donation(BaseDBModel):
    """Improved donation model with better validation and currency handling"""

    class CurrencyChoices(models.TextChoices):
        USD = 'USD', 'USD'
        NGN = 'NGN', 'NGN'

    class StatusChoices(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PROCESSING = 'PROCESSING', 'Processing'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        REFUNDED = 'REFUNDED', 'Refunded'

    class FrequencyChoices(models.TextChoices):
        ONCE = 'ONCE', 'One-time'
        MONTHLY = 'MONTHLY', 'Monthly'
        # Can add QUARTERLY, YEARLY etc. later

    class PaymentClientChoices(models.TextChoices):
        PAYSTACK = 'PAYSTACK', 'Paystack'
        PAYPAL = 'PAYPAL', 'PayPal'

    # Core donation fields

    project = models.ForeignKey(
        'Project',
        on_delete=models.CASCADE,
        related_name='donations',
        null=True, blank=True
    )

    # Donor information
    donor_email = models.EmailField(db_index=True)
    donor_full_name = models.CharField(max_length=255)

    # Amount and currency
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Amount in the currency the donor paid"
    )
    currency = models.CharField(
        max_length=3,
        choices=CurrencyChoices.choices,
        help_text="Currency the donor paid in"
    )

    # Converted amount (if needed for project currency)
    project_currency_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True, blank=True,
        help_text="Amount converted to project currency"
    )
    project_currency = models.CharField(
        max_length=3,
        choices=CurrencyChoices.choices,
        null=True, blank=True,
        help_text="Currency the project is in"
    )

    project_title = models.CharField(max_length=255, null=True, blank=True)

    exchange_rate_used = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True, blank=True,
        help_text="Exchange rate used for conversion"
    )

    # Donation details
    frequency = models.CharField(
        max_length=20,
        choices=FrequencyChoices.choices,
        default=FrequencyChoices.ONCE
    )
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING,
        db_index=True
    )

    # Payment processing fields
    payment_client = models.CharField(
        max_length=20,
        choices=PaymentClientChoices.choices,
        default=PaymentClientChoices.PAYSTACK
    )
    reference = models.CharField(
        max_length=200,
        unique=True,
        null=True,
        db_index=True,
        help_text="Payment gateway reference"
    )

    previous_amount_raised = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    current_amount_raised = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Subscription fields (for recurring donations)
    payment_plan_code = models.CharField(max_length=255, blank=True, null=True)
    agreement_id = models.CharField(
        max_length=200,
        blank=True, null=True,
        unique=True,
        help_text="For recurring payment agreements"
    )
    parent_donation = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='recurring_payments',
        help_text="Original donation for recurring payments"
    )

    # Metadata
    payment_completed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['donor_email', 'status']),
            models.Index(fields=['project', 'status']),
            models.Index(fields=['reference']),
        ]

    def save(self, *args, **kwargs):
        # Set payment completion timestamp
        if self.status == self.StatusChoices.COMPLETED \
                and not self.payment_completed_at:
            self.payment_completed_at = timezone.now()

        # Calculate converted amount if needed
        if self.project:
            self.convert_to_project_currency()

        super().save(*args, **kwargs)

        # Update project amounts if donation completed
        if (self.status == self.StatusChoices.COMPLETED and
                self.project):  # Only on creation, not updates
            self.project.add_donation_amount(self.get_project_amount())

    def convert_to_project_currency(self):
        """Convert donation amount to project currency"""

        self.project_currency = self.project.currency
        self.project_title = self.project.title
        if not self.project or self.currency == self.project.currency:
            self.project_currency_amount = self.amount
            self.exchange_rate_used = Decimal('1.0000')
            return

        try:
            current_rate = ExchangeRate.get_current_rate()
            if not current_rate:
                raise ValueError("No exchange rate available")

            self.project_currency_amount = ExchangeRate.convert_currency(
                self.amount,
                self.currency,
                self.project.currency
            )
            self.exchange_rate_used = current_rate.usd_to_ngn_rate

        except Exception as e:
            # Log the error but don't fail the save
            print(f"Currency conversion failed: {e}")
            self.project_currency_amount = self.amount

    def get_project_amount(self):
        """Get the amount in project currency"""
        return self.project_currency_amount or self.amount

    def is_recurring(self):
        """Check if this is a recurring donation"""
        return self.frequency != self.FrequencyChoices.ONCE

    def __str__(self):
        return f"{self.donor_full_name} ({self.get_status_display()})"


class Volunteer(BaseDBModel):
    """

    """
    ROLE_CHOICES = [
        ("lab-tech", "Lab Technician"),
        ("computer-tech", "Computer Technician"),
        ("medical-tech", "Medical Technician"),
        ("other", "Other"),
    ]
    AVAILABILITY_CHOICES = [
        ("full-time", "Full Time"),
        ("part-time", "Part Time"),
    ]

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    age = models.PositiveIntegerField()
    phone_number = models.CharField(max_length=12, blank=True, null=True)
    email = models.EmailField(max_length=150, blank=True, null=True)
    country = models.CharField(max_length=100)
    role = models.CharField(max_length=50, choices=ROLE_CHOICES)
    availability = models.CharField(max_length=50, choices=AVAILABILITY_CHOICES)
    hours = models.CharField(max_length=50, blank=True, null=True)
    days = models.CharField(max_length=50, blank=True, null=True)
    cv = models.FileField(upload_to='volunteer_cvs/')

    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.role}"


class Subscription(BaseDBModel):
    email = models.EmailField(unique=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.email
