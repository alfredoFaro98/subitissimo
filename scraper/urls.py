from django.urls import path
from . import views

urlpatterns = [
    path('', views.search_view, name='search'),
    path('results/', views.results_view, name='results'),
    path('results/map/', views.map_view, name='map_view'),
]
