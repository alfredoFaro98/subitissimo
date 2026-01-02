from django.db import models

class SearchQuery(models.Model):
    query = models.CharField(max_length=255)
    limit = models.IntegerField(default=35)
    title_only = models.BooleanField(default=False)
    shippable_only = models.BooleanField(default=False)
    region = models.CharField(max_length=100, blank=True, null=True)
    province = models.CharField(max_length=100, blank=True, null=True)
    total_results = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.query

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
    region = models.CharField(max_length=100, blank=True, null=True)
    province = models.CharField(max_length=100, blank=True, null=True)
    date_saved = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.query
