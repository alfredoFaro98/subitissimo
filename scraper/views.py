from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from .models import SearchQuery, Item
from .services import run_search

def search_view(request):
    if request.method == 'POST':
        query = request.POST.get('query')
        limit = int(request.POST.get('limit', 35))
        title_only = request.POST.get('title_only') == 'on'
        if query:
            search_obj = run_search(query, limit=limit, title_only=title_only)
            return redirect('results', search_id=search_obj.id)
    return render(request, 'scraper/search.html')

def results_view(request, search_id):
    search_obj = get_object_or_404(SearchQuery, id=search_id)
    items = search_obj.items.all()
    
    # Simple server-side sorting if requested (though we plan client-side too)
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
