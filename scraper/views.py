import csv
import json
from collections import Counter
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.core import serializers
from django.utils.text import slugify
from .services import run_search
from .models import GeoCache
from .cities_data import ITALIAN_CITIES
from .categories import MACROCATEGORIES, CATEGORY_NAMES


def get_current_search_items(request):
    items_data = request.session.get('search_results', [])
    processed_items = []

    for item in items_data:
        new_item = item.copy()
        if new_item.get('date_pub_iso'):
            try:
                new_item['date_pub_iso'] = datetime.fromisoformat(new_item['date_pub_iso'])
            except (TypeError, ValueError):
                pass
        processed_items.append(new_item)

    shippable_param = request.GET.get('shippable')
    if shippable_param == 'true':
        processed_items = [i for i in processed_items if i.get('shippable')]
    elif shippable_param == 'false':
        processed_items = [i for i in processed_items if not i.get('shippable')]

    category_param = request.GET.get('category')
    if category_param:
        processed_items = [i for i in processed_items if i.get('category') == category_param]

    sort_by = request.GET.get('sort')

    def get_price(i):
        return i.get('price_num') or 0.0

    def get_date_timestamp(i):
        d = i.get('date_pub_iso')
        if isinstance(d, datetime):
            return d.timestamp()
        return 0.0

    if sort_by == 'price_asc':
        processed_items.sort(key=get_price)
    elif sort_by == 'price_desc':
        processed_items.sort(key=get_price, reverse=True)
    elif sort_by == 'date_asc':
        processed_items.sort(key=get_date_timestamp)
    else:
        processed_items.sort(key=get_date_timestamp, reverse=True)

    return processed_items

def search_view(request):
    error = ''
    if request.method == 'POST':
        query = (request.POST.get('query') or '').strip()
        limit = int(request.POST.get('limit', 35))
        title_only = request.POST.get('title_only') == 'on'
        shippable_only = request.POST.get('shippable_only') == 'on'
        category = request.POST.get('category', '')
        if category not in CATEGORY_NAMES:
            category = ''
        if query or category:
            items_list = run_search(query, limit=limit, title_only=title_only, shippable_only=shippable_only, category=category)
            
            # Save results to session
            request.session['search_results'] = items_list
            request.session['search_query'] = query
            request.session['search_category'] = category
            request.session['total_results'] = len(items_list) # Simplified count
            
            return redirect('results')
        error = 'Scrivi cosa cerchi oppure scegli una categoria.'
    return render(request, 'scraper/search.html', {'macrocategories': MACROCATEGORIES, 'error': error})

def results_view(request):
    query = request.session.get('search_query', 'Unknown')
    total_results = request.session.get('total_results', 0)
    processed_items = get_current_search_items(request)
    category_counts = Counter(
        i.get('category') for i in request.session.get('search_results', []) if i.get('category')
    )
    
    # Mark favorites
    favorite_ids = set(Favorite.objects.values_list('subito_id', flat=True))
    for item in processed_items:
        if item.get('subito_id') in favorite_ids:
            item['is_favorite'] = True
    
    # Mock a search object for the template to display the title
    class MockSearch:
        def __init__(self, q, count):
            self.query = q
            self.total_results = count
            
    context = {
        'search': MockSearch(query, total_results),
        'items': processed_items,
        'category_counts': category_counts.most_common(),
        'search_category_name': CATEGORY_NAMES.get(request.session.get('search_category', ''), ''),
    }
    return render(request, 'scraper/results.html', context)


def export_results_csv(request):
    query = request.session.get('search_query', 'ricerca')
    items = get_current_search_items(request)

    filename_query = slugify(query) or 'ricerca'
    filename = f"subitissimo_{filename_query}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')

    writer = csv.writer(response, delimiter=';')
    writer.writerow([
        'Titolo',
        'Prezzo',
        'Prezzo numerico',
        'Data pubblicazione',
        'Categoria',
        'Regione',
        'Provincia',
        'Comune',
        'Condizione',
        'Spedibile',
        'Tipo spedizione',
        'Costo spedizione',
        'Like',
        'Stato',
        'Motivo stato',
        'Descrizione',
        'Link annuncio',
        'Link immagine',
        'ID Subito',
    ])

    for item in items:
        date_iso = item.get('date_pub_iso')
        if isinstance(date_iso, datetime):
            date_iso = date_iso.isoformat()

        writer.writerow([
            item.get('title') or '',
            item.get('price_str') or '',
            item.get('price_num') if item.get('price_num') is not None else '',
            item.get('date_pub') or date_iso or '',
            item.get('category') or '',
            item.get('region') or '',
            item.get('province') or '',
            item.get('town') or '',
            item.get('condition') or '',
            'Si' if item.get('shippable') else 'No',
            item.get('shipping_type') or '',
            item.get('shipping_cost') if item.get('shipping_cost') is not None else '',
            item.get('likes_count') if item.get('likes_count') is not None else '',
            item.get('defect_flag') or '',
            item.get('defect_reason') or '',
            item.get('description') or '',
            item.get('url') or '',
            item.get('image_url') or '',
            item.get('subito_id') or '',
        ])

    return response

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
