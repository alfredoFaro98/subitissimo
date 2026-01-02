from django.urls import path
from . import views

urlpatterns = [
    path('', views.search_view, name='search'),
    path('results/', views.results_view, name='results'),
    path('results/map/', views.map_view, name='map_view'),
    
    # New Persistence Features
    path('history/', views.history_view, name='history'),
    path('favorites/', views.favorites_view, name='favorites'),
    path('saved/', views.saved_searches_view, name='saved_searches'),
    
    # Actions
    path('api/toggle_favorite/', views.toggle_favorite, name='toggle_favorite'),
    path('api/save_search/', views.save_search, name='save_search'),
    path('api/delete_history/<int:pk>/', views.delete_history, name='delete_history'),
    path('api/delete_saved/<int:pk>/', views.delete_saved_search, name='delete_saved_search'),
]
