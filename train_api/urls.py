from django.urls import path
from . import views

urlpatterns = [
    path('getTrain', views.get_train_view, name='get-train'),
    path('betweenStations', views.between_stations_view, name='between-stations'),
    path('getTrainOn', views.get_train_on_view, name='get-train-on'),
    path('getRoute', views.get_route_view, name='get-route'),
    path('stationLive', views.station_live_view, name='station-live'),
    path('pnrstatus', views.pnr_status_view, name='pnr-status'),
]