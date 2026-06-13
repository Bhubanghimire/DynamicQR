from django.db import models

from accounts.views import User
from system.models import ConfigChoice, SoftDeletable


# Create your models here.
class Project(SoftDeletable):
    owner = models.ForeignKey(User, on_delete=models.RESTRICT)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    # industry = models.ForeignKey(ConfigChoice, on_delete=models.RESTRICT)
    status = models.ForeignKey(ConfigChoice, on_delete=models.RESTRICT)

    def __str__(self):
        return self.name