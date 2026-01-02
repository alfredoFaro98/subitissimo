from django.urls import path
from . import views

urlpatterns = [
    path('', views.search_view, name='search'),
    path('results/<int:search_id>/', views.results_view, name='results'),
    path('results/<int:search_id>/map/', views.map_view, name='results_map'),
]
