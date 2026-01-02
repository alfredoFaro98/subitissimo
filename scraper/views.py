from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from .models import SearchQuery, Item
from .services import run_search

def search_view(request):
    if request.method == 'POST':
        query = request.POST.get('query')
        limit = int(request.POST.get('limit', 35))
        title_only = request.POST.get('title_only') == 'on'
        shippable_only = request.POST.get('shippable_only') == 'on'
        if query:
            search_obj = run_search(query, limit=limit, title_only=title_only, shippable_only=shippable_only)
            return redirect('results', search_id=search_obj.id)
    return render(request, 'scraper/search.html')

def results_view(request, search_id):
    search_obj = get_object_or_404(SearchQuery, id=search_id)
    items = search_obj.items.all()
    
    # Filter by shipping if requested on results page
    shippable_param = request.GET.get('shippable')
    if shippable_param == 'true':
        items = items.filter(shippable=True)
    elif shippable_param == 'false':
        items = items.filter(shippable=False)
    
    # Simple server-side sorting
    sort_by = request.GET.get('sort')
    if sort_by == 'price_asc':
        items = items.order_by('price_num')
    elif sort_by == 'price_desc':
        items = items.order_by('-price_num')
    elif sort_by == 'date_desc':
        items = items.order_by('-date_pub_iso')
    elif sort_by == 'date_asc':
        items = items.order_by('date_pub_iso')
    else:
        # Default sort
        items = items.order_by('-date_pub_iso')
    
    context = {
        'search': search_obj,
        'items': items,
    }
    return render(request, 'scraper/results.html', context)

from django.core.serializers import serialize
import json
from .cities_data import ITALIAN_CITIES
from .models import GeoCache

def map_view(request, search_id):
    search_obj = get_object_or_404(SearchQuery, id=search_id)
    items = search_obj.items.all()
    
    # Pre-process items to attach coordinates from Cache or Static Data
    items_json_str = serialize('json', items)
    items_data = json.loads(items_json_str)
    
    # Collect all needed locations
    locations = set()
    for item_dict in items_data:
        fields = item_dict['fields']
        town = (fields.get('town') or "").strip().lower()
        prov = (fields.get('province') or "").strip().lower()
        
        # Priority: town, then province
        loc_key = town if town else prov
        if loc_key:
            locations.add(loc_key)
            item_dict['location_key'] = loc_key # Store for later match
    
    # 1. Fetch from DB Cache
    cached_map = {}
    db_caches = GeoCache.objects.filter(location_key__in=locations)
    for c in db_caches:
        cached_map[c.location_key] = (c.latitude, c.longitude)
        
    # 2. Check Static Data and Update DB if needed
    for loc in locations:
        if loc not in cached_map:
            # Check static list
            if loc in ITALIAN_CITIES:
                lat, lon = ITALIAN_CITIES[loc]
                cached_map[loc] = (lat, lon)
                # Async save to DB for future would be better, but sync is fine here
                GeoCache.objects.create(location_key=loc, latitude=lat, longitude=lon)
    
    # 3. Attach coords to items_data
    for item_dict in items_data:
        loc_key = item_dict.get('location_key')
        if loc_key and loc_key in cached_map:
            lat, lon = cached_map[loc_key]
            item_dict['lat'] = lat
            item_dict['lon'] = lon
    
    context = {
        'search': search_obj,
        'items': items,
        'items_data': items_data,
    }
    return render(request, 'scraper/map.html', context)
