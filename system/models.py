import uuid

from django.db import models
from django.utils import timezone


# Create your models here.
class ConfigCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ConfigChoice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(ConfigCategory, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    image = models.ImageField(upload_to='choice/', null=True, blank=True)
    status = models.BooleanField(default=True)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        unique_together = ('category', 'name',)


class SoftDeletableManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def get_deleted(self):
        return super().get_queryset().filter(is_deleted=True)


class SoftDeletable(models.Model):
    """
    An abstract model that adds soft-delete functionality to any model that inherits it.

    Fields:
        - `is_deleted` (BooleanField): Indicates whether the object has been soft-deleted. Default is False.
        - `deleted_at` (DateTimeField): Timestamp indicating when the object was soft-deleted. Null if not deleted.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_deleted = models.BooleanField(default=False, help_text="Indicates whether this object has been soft-deleted.")
    deleted_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when the object was soft-deleted.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SoftDeletableManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """
        Soft-deletes the object by setting `is_deleted` to True and updating `deleted_at` with the current timestamp.
        """
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()

    def hard_delete(self):
        """
        Permanently deletes the object from the database, bypassing the soft-delete mechanism.
        """
        super(SoftDeletable, self).delete()

    def restore(self):
        """
        Restores a soft-deleted object by setting `is_deleted` to False and clearing the `deleted_at` timestamp.
        """
        self.__class__.objects.get_deleted().filter(pk=self.pk).update(is_deleted=False, deleted_at=None)
        self.refresh_from_db()
