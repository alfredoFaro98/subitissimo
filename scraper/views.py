import json
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.core import serializers
from .services import run_search
from .models import GeoCache
from .cities_data import ITALIAN_CITIES

def search_view(request):
    if request.method == 'POST':
        query = request.POST.get('query')
        limit = int(request.POST.get('limit', 35))
        title_only = request.POST.get('title_only') == 'on'
        shippable_only = request.POST.get('shippable_only') == 'on'
        if query:
            items_list = run_search(query, limit=limit, title_only=title_only, shippable_only=shippable_only)
            
            # Save results to session
            request.session['search_results'] = items_list
            request.session['search_query'] = query
            request.session['total_results'] = len(items_list) # Simplified count
            
            return redirect('results')
    return render(request, 'scraper/search.html')

def results_view(request):
    # Get items from session
    items_data = request.session.get('search_results', [])
    query = request.session.get('search_query', 'Unknown')
    total_results = request.session.get('total_results', 0)
    
    # Process items (restore datetime objects for sorting/filtering/display)
    # We essentially treat them as objects to match template usage as much as possible, 
    # but they are dicts, so we can access them as such. However, Django templates 
    # access dict keys via dot notation, so {{ item.title }} works for dicts too.
    
    processed_items = []
    for item in items_data:
        # Clone to avoid modifying session data in place (though session is re-saved only on modify)
        # But we need to parse dates
        new_item = item.copy()
        if new_item.get('date_pub_iso'):
            try:
                new_item['date_pub_iso'] = datetime.fromisoformat(new_item['date_pub_iso'])
            except:
                pass
        processed_items.append(new_item)

    # Filter by shipping if requested on results page
    shippable_param = request.GET.get('shippable')
    if shippable_param == 'true':
        processed_items = [i for i in processed_items if i.get('shippable')]
    elif shippable_param == 'false':
        processed_items = [i for i in processed_items if not i.get('shippable')]
    
    # Mark favorites
    favorite_ids = set(Favorite.objects.values_list('subito_id', flat=True))
    for item in processed_items:
        if item.get('subito_id') in favorite_ids:
            item['is_favorite'] = True
    
    # Simple server-side sorting (In-Memory)
    sort_by = request.GET.get('sort')
    
    def get_price(i):
        return i.get('price_num') or 0.0

    def get_date(i):
        # We need to handle potential string/datetime mismatch if logic fails, but we parsed above
        d = i.get('date_pub_iso')
        if not d:
            return datetime.min
        return d

    if sort_by == 'price_asc':
        processed_items.sort(key=get_price)
    elif sort_by == 'price_desc':
        processed_items.sort(key=get_price, reverse=True)
    elif sort_by == 'date_desc':
        processed_items.sort(key=get_date, reverse=True)
    elif sort_by == 'date_asc':
        processed_items.sort(key=get_date)
    else:
        # Default sort
        processed_items.sort(key=get_date, reverse=True)
    
    # Mock a search object for the template to display the title
    class MockSearch:
        def __init__(self, q, count):
            self.query = q
            self.total_results = count
            
    context = {
        'search': MockSearch(query, total_results),
        'items': processed_items,
    }
    return render(request, 'scraper/results.html', context)

def map_view(request):
    # Get items from session
    raw_items = request.session.get('search_results', [])
    
    # Geocoding logic
    # We need to extract locations and coordinates
    items_data = []
    
    for item in raw_items:
        # ... logic similar to previous but using dict access ...
        town = (item.get('town') or '').lower().strip()
        province = (item.get('province') or '').lower().strip()
        region = (item.get('region') or '').lower().strip()
        
        # ... (Geocoding logic remains mostly same, just adapt key access)
        location_key = f"{town}" or f"{province}"
        if not location_key and region:
            location_key = region
            
        lat = None
        lon = None
        
        if location_key:
             # Check DB cache first
            cached = GeoCache.objects.filter(location_key=location_key).first()
            if cached:
                lat = cached.latitude
                lon = cached.longitude
            else:
                 # Check static list
                if location_key in ITALIAN_CITIES:
                    coords = ITALIAN_CITIES[location_key]
                    lat = coords[0]
                    lon = coords[1]
                    # Update cache
                    GeoCache.objects.create(location_key=location_key, latitude=lat, longitude=lon)
        
        # Add lat/lon to display item
        # We create a new dict for display
        display_item = item.copy()
        display_item['lat'] = lat
        display_item['lon'] = lon
        items_data.append(display_item)

    # Use json.dumps for the script, but we need to serialize dates/floats carefully
    # The existing template expects 'items_data' generic variable
    # We can pass the items_data list directly to json_script if clean
    
    # Clean for JSON
    json_items = []
    for i in items_data:
        j_item = i.copy()
        # Remove non-serializable objects if any (datetime)
        if 'date_pub_iso' in j_item:
            # It's a string in the session, but we might have parsed it if we reused logic?
            # In session it is string. In raw_items it is string.
            pass 
        json_items.append(j_item)
        
    context = {
        'items_data_json': json.dumps(json_items) # Pass as string to be used safely
    }
    return render(request, 'scraper/map.html', context)

# Persistence Views
from .models import SearchQuery, Favorite, SavedSearch
from django.views.decorators.http import require_POST
from django.contrib import messages

def history_view(request):
    searches = SearchQuery.objects.all().order_by('-created_at')
    return render(request, 'scraper/history.html', {'searches': searches})

def favorites_view(request):
    favorites = Favorite.objects.all().order_by('-date_added')
    return render(request, 'scraper/favorites.html', {'favorites': favorites})

def saved_searches_view(request):
    saved = SavedSearch.objects.all().order_by('-date_saved')
    return render(request, 'scraper/saved_searches.html', {'saved': saved})

@require_POST
def toggle_favorite(request):
    try:
        data = json.loads(request.body)
        subito_id = data.get('subito_id')
        
        if not subito_id:
            return JsonResponse({'status': 'error', 'message': 'Missing ID'}, status=400)
            
        fav = Favorite.objects.filter(subito_id=subito_id).first()
        if fav:
            fav.delete()
            return JsonResponse({'status': 'removed'})
        else:
            # Create new favorite
            Favorite.objects.create(
                subito_id=subito_id,
                title=data.get('title'),
                price_str=data.get('price_str'),
                price_num=data.get('price_num') if data.get('price_num') else None,
                url=data.get('url'),
                image_url=data.get('image_url'),
                town=data.get('town'),
                region=data.get('region')
            )
            return JsonResponse({'status': 'added'})
            
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_POST
def save_search(request):
    try:
        data = json.loads(request.body)
        query = data.get('query')
        
        if not query:
            return JsonResponse({'status': 'error', 'message': 'Missing query'}, status=400)
            
        SavedSearch.objects.create(
            query=query,
            min_price=data.get('min_price'),
            max_price=data.get('max_price')
        )
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_POST
def delete_history(request, pk):
    get_object_or_404(SearchQuery, pk=pk).delete()
    return redirect('history')

@require_POST
def delete_saved_search(request, pk):
    get_object_or_404(SavedSearch, pk=pk).delete()
    return redirect('saved_searches')
