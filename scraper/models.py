from django.db import models
from .categories import CATEGORY_NAMES

class SearchQuery(models.Model):
    query = models.CharField(max_length=255)
    limit = models.IntegerField(default=35)
    title_only = models.BooleanField(default=False)
    shippable_only = models.BooleanField(default=False)
    category = models.CharField(max_length=10, blank=True, default='')
    total_results = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.query

    @property
    def category_name(self):
        return CATEGORY_NAMES.get(self.category, '')

class Item(models.Model):
    search_query = models.ForeignKey(SearchQuery, on_delete=models.CASCADE, related_name='items')
    subito_id = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    price_str = models.CharField(max_length=50, blank=True, null=True)
    price_num = models.FloatField(blank=True, null=True)
    
    # Dates
    date_pub = models.CharField(max_length=100, blank=True, null=True)
    date_pub_iso = models.DateTimeField(blank=True, null=True)
    date_expiration = models.DateTimeField(blank=True, null=True)
    
    # Category / Location
    category = models.CharField(max_length=100, blank=True, null=True)
    region = models.CharField(max_length=100, blank=True, null=True)
    province = models.CharField(max_length=100, blank=True, null=True)
    town = models.CharField(max_length=100, blank=True, null=True)
    
    # Details
    condition = models.CharField(max_length=50, blank=True, null=True)
    shipping_type = models.CharField(max_length=50, blank=True, null=True)
    shipping_cost = models.FloatField(blank=True, null=True)
    shippable = models.BooleanField(default=False)
    likes_count = models.IntegerField(default=0, blank=True, null=True)
    
    # Media
    image_url = models.URLField(max_length=1000, blank=True, null=True)
    url = models.URLField(max_length=1000)
    
    class Meta:
        ordering = ['-date_pub_iso']

    def __str__(self):
        return self.title

class GeoCache(models.Model):
    location_key = models.CharField(max_length=255, unique=True, db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.location_key} ({self.latitude}, {self.longitude})"

class Favorite(models.Model):
    subito_id = models.CharField(max_length=255, unique=True)
    title = models.CharField(max_length=255)
    price_str = models.CharField(max_length=50, blank=True, null=True)
    price_num = models.FloatField(blank=True, null=True)
    url = models.URLField(max_length=1000)
    image_url = models.URLField(max_length=1000, blank=True, null=True)
    town = models.CharField(max_length=100, blank=True, null=True)
    region = models.CharField(max_length=100, blank=True, null=True)
    date_added = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class SavedSearch(models.Model):
    query = models.CharField(max_length=255)
    min_price = models.FloatField(blank=True, null=True)
    max_price = models.FloatField(blank=True, null=True)
    date_saved = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.query


class Monitor(models.Model):
    """Una ricerca sorvegliata in continuo dal comando `manage.py monitor`."""
    name = models.CharField(max_length=120, blank=True, default='')
    query = models.CharField(max_length=255, blank=True, default='')
    category = models.CharField(max_length=10, blank=True, default='')
    title_only = models.BooleanField(default=False)
    shippable_only = models.BooleanField(default=False)
    interval_seconds = models.IntegerField(default=30)
    page_size = models.IntegerField(default=50)
    is_active = models.BooleanField(default=True)
    is_seeded = models.BooleanField(default=False)
    seeded_at = models.DateTimeField(blank=True, null=True)
    last_checked_at = models.DateTimeField(blank=True, null=True)
    last_hit_at = models.DateTimeField(blank=True, null=True)
    checks_count = models.IntegerField(default=0)
    last_error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.label

    @property
    def category_name(self):
        return CATEGORY_NAMES.get(self.category, '')

    @property
    def label(self):
        if self.name:
            return self.name
        parts = [p for p in (self.query, self.category_name) if p]
        return ' · '.join(parts) or 'Monitor'


class MonitorHit(models.Model):
    """Annuncio visto per la prima volta da un Monitor. Non viene mai cancellato:
    se l'annuncio sparisce da Subito la riga resta, cosi' si vede cosa e' passato."""
    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name='hits')
    subito_id = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    price_str = models.CharField(max_length=50, blank=True, null=True)
    price_num = models.FloatField(blank=True, null=True)

    date_pub = models.CharField(max_length=100, blank=True, null=True)
    date_pub_iso = models.DateTimeField(blank=True, null=True)

    category = models.CharField(max_length=100, blank=True, null=True)
    region = models.CharField(max_length=100, blank=True, null=True)
    province = models.CharField(max_length=100, blank=True, null=True)
    town = models.CharField(max_length=100, blank=True, null=True)

    condition = models.CharField(max_length=50, blank=True, null=True)
    shipping_type = models.CharField(max_length=50, blank=True, null=True)
    shipping_cost = models.FloatField(blank=True, null=True)
    shippable = models.BooleanField(default=False)

    image_url = models.URLField(max_length=1000, blank=True, null=True)
    url = models.URLField(max_length=1000)
    description = models.TextField(blank=True, default='')
    defect_flag = models.CharField(max_length=50, blank=True, default='')
    defect_reason = models.CharField(max_length=255, blank=True, default='')

    first_seen_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_read = models.BooleanField(default=False)
    is_seed = models.BooleanField(default=False)
    # quando la riga e' stata scritta nel CSV; None = ancora da scrivere
    exported_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-first_seen_at']
        constraints = [
            models.UniqueConstraint(fields=['monitor', 'subito_id'], name='uniq_monitor_subito_id'),
        ]

    def __str__(self):
        return self.title
