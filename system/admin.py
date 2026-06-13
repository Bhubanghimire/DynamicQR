from django.contrib import admin
from system.models import ConfigCategory, ConfigChoice


# Register your models here.
@admin.register(ConfigCategory)
class ConfigCategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')


@admin.register(ConfigChoice)
class ConfigChoiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    list_filter = ('category',)