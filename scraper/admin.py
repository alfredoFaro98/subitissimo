from django.contrib import admin
from .models import SearchQuery, Item, Monitor, MonitorHit

admin.site.register(SearchQuery)
admin.site.register(Item)


@admin.register(Monitor)
class MonitorAdmin(admin.ModelAdmin):
    list_display = ('label', 'category_name', 'interval_seconds', 'is_active',
                    'checks_count', 'last_checked_at', 'last_error')
    list_filter = ('is_active', 'category')


@admin.register(MonitorHit)
class MonitorHitAdmin(admin.ModelAdmin):
    list_display = ('first_seen_at', 'price_str', 'title', 'town', 'category',
                    'monitor', 'is_seed')
    list_filter = ('monitor', 'is_seed', 'is_read', 'shippable', 'category')
    search_fields = ('title', 'subito_id', 'town')
    date_hierarchy = 'first_seen_at'
