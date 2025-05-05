from django.contrib import admin
from .models import Apporteur

@admin.register(Apporteur)
class ApporteurAdmin(admin.ModelAdmin):
    list_display = ('user', 'pourcentage_prime')

