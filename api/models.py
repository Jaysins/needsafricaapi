from django.db import models
from core.models import BaseDBModel
from decimal import Decimal
from django.contrib.auth.models import AbstractUser

# Create your models here.

class User(AbstractUser,BaseDBModel):
    username = models.CharField(max_length=140, blank=True, null=True,
                                unique=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return self.username
    



class Project(BaseDBModel):

    CURRENCY_CHOICES = [
        ('USD', 'USD'),
        ('NGN', 'NGN'),
    ]

    CATEGORY_CHOICES = [
        ('education', 'Education'),
        ('healthcare', 'Healthcare'),
    ]
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True, null=True)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deadline = models.DateField(blank=True, null=True)
    receiving_donation = models.BooleanField(default=True,blank=True, null=True)
    
    amount_raised = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    percentage_funded = models.FloatField(default=0.0)
    remaining_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    donation_reason = models.CharField(max_length=150, blank=True, null=True)

    milestones = models.TextField(help_text="List of completed actions, as bullet points", blank=True, null=True)

    location = models.CharField(max_length=150, blank=True, null=True)
    cover_image = models.ImageField(upload_to='project_covers/', blank=True, null=True)
    amount_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, blank=True, null=True)
    status = models.CharField(max_length=20, default='ACTIVE', choices=[
        ('ACTIVE', 'ACTIVE'),
        ('COMPLETED', 'COMPLETED'),
        ('CANCELLED', 'CANCELLED'),
    ])
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD')

  

    def update_progress(self):
        if self.target_amount > 0:
            self.percentage_funded = float((self.amount_raised / self.target_amount) * 100)
            self.remaining_amount = self.target_amount - self.amount_raised
        else:
            self.percentage_funded = 0.0
            self.remaining_amount = Decimal("0.00")
        self.save()

    def __str__(self):
        return f"{self.title} - {self.percentage_funded:.1f}% funded"

#proof of delivery
class ProjectPhoto(BaseDBModel):
    name= models.CharField(max_length=150, blank=True, null=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='project_photos/')
    deliver_date = models.DateField(blank=True, null=True)
    def __str__(self):
        return f"Photo for {self.project.title}"

class Donation(BaseDBModel):
    CURRENCY_CHOICES = [
        ('USD', 'USD'),
        ('NGN', 'NGN'),
    ]
    
    class DonationStatus(models.TextChoices):
        PENDING = 'PENDING', 'PENDING'
        COMPLETED = 'COMPLETED', 'COMPLETED'
        CANCELLED = 'CANCELLED', 'CANCELLED'

    class FrequnceyChoice(models.TextChoices):
        ONCE = 'ONCE', 'ONCE'
        MONTHLY = 'MONTHLY', 'MONTHLY'

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='donations', blank=True, null=True)
    donor_email = models.EmailField()
    donor_full_name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES)
    frequency = models.CharField(max_length=150, default=FrequnceyChoice.ONCE.value, choices=FrequnceyChoice.choices)
    status = models.CharField(default=DonationStatus.PENDING.value, max_length=20, choices=DonationStatus.choices)
    payment_plan_code = models.CharField(max_length=255, blank=True, null=True)
    payment_client= models.CharField(max_length=255, blank=True, null=True, default="PAYSTACK")
    reference = models.CharField(max_length=200, blank=True, null=True)
    agreement_id = models.CharField(max_length=200, blank=True, null=True, unique=True)
    def __str__(self):
        return f"{self.donor_full_name} donated {self.amount} {self.currency.upper()}"