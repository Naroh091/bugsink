from django.contrib import admin

from .models import MessagingServiceConfig


@admin.register(MessagingServiceConfig)
class MessagingServiceConfigAdmin(admin.ModelAdmin):
    list_display = ('team', 'display_name', 'kind', 'last_failure_timestamp')
    search_fields = ('display_name',)
    list_filter = ('kind',)
    filter_horizontal = ('projects',)
