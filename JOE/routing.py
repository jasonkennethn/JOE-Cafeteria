from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/order/(?P<order_id>\w+)/$', consumers.OrderLiveTrackerConsumer.as_asgi()),
    re_path(r'ws/kitchen/$', consumers.KitchenDashboardConsumer.as_asgi()),
    re_path(r'ws/serving/$', consumers.ServingDeskConsumer.as_asgi()),
    re_path(r'ws/inventory/$', consumers.InventoryConsumer.as_asgi()),
    re_path(r'ws/notifications/$', consumers.NotificationConsumer.as_asgi()),
    re_path(r'ws/cart-reservations/$', consumers.CartReservationConsumer.as_asgi()),
]
