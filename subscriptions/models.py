from django.db import models

from accounts.models import User
from system.models import SoftDeletable, ConfigChoice


# Create your models here.
class Package(SoftDeletable):
    title = models.CharField(max_length=100)
    description = models.TextField()
    is_active = models.BooleanField(default=True)


    def __str__(self):
        return self.title



class PackagePlan(SoftDeletable):
    package = models.ForeignKey(Package, on_delete=models.SET_NULL, null=True)
    billing_period = models.CharField(max_length=100, choices=[('Monthly', 'Monthly'), ('Yearly', 'Yearly')])
    price =models.DecimalField(max_digits=10, decimal_places=2)
    currency =models.CharField(max_length=10)
    duration_days = models.IntegerField(default=0)

    def __str__(self):
        return self.package


class PackageLimit(SoftDeletable):
    package = models.ForeignKey(Package, on_delete=models.SET_NULL, null=True)
    max_qrs = models.IntegerField(default=0)
    max_scans = models.IntegerField(default=0)
    max_team_members = models.IntegerField(default=0)


class PackageFeature(SoftDeletable):
    class Feature(models.TextChoices):
        ADVANCED_ANALYTICS = "advanced_analytics", "Advanced Analytics"
        CUSTOM_BRANDING = "custom_branding", "Custom Branding"
        API_ACCESS = "api_access", "API Access"
        CUSTOM_DOMAIN = "custom_domain", "Custom Domain"
        BULK_IMPORT = "bulk_import", "Bulk Import"

    package = models.ForeignKey(Package, on_delete=models.RESTRICT)
    feature = models.CharField(max_length=100, choices=Feature.choices)
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.package





class Subscription(SoftDeletable):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    package_plan =models.ForeignKey(PackagePlan, on_delete=models.RESTRICT)
    started_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    status = models.ForeignKey(ConfigChoice, on_delete=models.SET_NULL, null=True)
    auto_renew =models.BooleanField(default=False)




class Invoice(SoftDeletable):

        class Status(models.TextChoices):
            DRAFT = "draft", "Draft"
            PENDING = "pending", "Pending"
            PAID = "paid", "Paid"
            OVERDUE = "overdue", "Overdue"
            CANCELLED = "cancelled", "Cancelled"
            REFUNDED = "refunded", "Refunded"

        invoice_number = models.CharField(max_length=50,unique=True)
        user = models.ForeignKey(User,on_delete=models.PROTECT,related_name="invoices")
        subscription = models.ForeignKey(Subscription,on_delete=models.PROTECT,related_name="invoices",null=True,blank=True)
        package_plan = models.ForeignKey(PackagePlan,on_delete=models.PROTECT,related_name="invoices",)
        amount = models.DecimalField(max_digits=12,decimal_places=2)
        tax = models.DecimalField(max_digits=12,decimal_places=2,default=0)
        total = models.DecimalField(max_digits=12,decimal_places=2)
        currency = models.CharField(max_length=3,default="NPR")
        due_date = models.DateTimeField()
        status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING,)
        issued_at = models.DateTimeField(auto_now_add=True)
        paid_at = models.DateTimeField(null=True,blank=True)
        created_at = models.DateTimeField(auto_now_add=True)
        updated_at = models.DateTimeField(auto_now=True)

        def __str__(self):
            return self.invoice_number


class Payment(SoftDeletable):

        class Status(models.TextChoices):
            PENDING = "pending", "Pending"
            SUCCESS = "success", "Success"
            FAILED = "failed", "Failed"
            CANCELLED = "cancelled", "Cancelled"
            REFUNDED = "refunded", "Refunded"

        user = models.ForeignKey(User,on_delete=models.PROTECT,related_name="payments")
        subscription = models.ForeignKey(Subscription,on_delete=models.PROTECT,related_name="payments")
        invoice = models.ForeignKey( Invoice, on_delete=models.PROTECT, related_name="payments")
        amount = models.DecimalField( max_digits=12, decimal_places=2)
        currency = models.CharField( max_length=3, default="NPR")
        provider = models.CharField( max_length=20, default="dodo")
        transaction_id = models.CharField( max_length=255, unique=True)
        status = models.CharField( max_length=20, choices=Status.choices, default=Status.PENDING)
        paid_at = models.DateTimeField(null=True,blank=True)
        created_at = models.DateTimeField(auto_now_add=True)
        updated_at = models.DateTimeField(auto_now=True)

        def __str__(self):
            return f"{self.transaction_id} - {self.amount} {self.currency}"




