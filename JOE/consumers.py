import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Order, OrderItem, MenuItem, CartItem
from django.utils import timezone
from datetime import timedelta

class OrderLiveTrackerConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.order_id = self.scope['url_route']['kwargs']['order_id']
        self.room_group_name = f'order_{self.order_id}'

        # Join the order specific group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        
        # Send current order status
        order_data = await self.get_order_data()
        if order_data:
            await self.send(text_data=json.dumps({
                'type': 'initial_status',
                'data': order_data
            }))

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def status_update(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps(event['data']))
    
    async def progress_update(self, event):
        # Send progress update to WebSocket
        await self.send(text_data=json.dumps(event['data']))
    
    @database_sync_to_async
    def get_order_data(self):
        try:
            order = Order.objects.get(id=self.order_id)
            items_data = []
            for item in order.items.all():
                items_data.append({
                    'id': item.id,
                    'name': item.menu_item.name,
                    'quantity': item.quantity,
                    'status': item.status,
                    'price': str(item.price_at_time),
                })
            
            return {
                'type': 'order_status',
                'order_id': order.id,
                'status': order.status,
                'total_amount': str(order.total_amount),
                'created_at': order.created_at.isoformat(),
                'ready_at': order.ready_at.isoformat() if order.ready_at else None,
                'items': items_data,
            }
        except Order.DoesNotExist:
            return None


class KitchenDashboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'kitchen'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def stock_update(self, event):
        await self.send(text_data=json.dumps(event['data']))
    
    async def order_update(self, event):
        await self.send(text_data=json.dumps(event['data']))

    async def menu_update(self, event):
        await self.send(text_data=json.dumps(event['data']))


class ServingDeskConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'serving'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def serving_update(self, event):
        await self.send(text_data=json.dumps(event['data']))
    
    async def order_update(self, event):
        await self.send(text_data=json.dumps(event['data']))


class InventoryConsumer(AsyncWebsocketConsumer):
    """Handles real-time stock updates for menu page"""
    async def connect(self):
        self.room_group_name = 'inventory'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        
        # Send initial stock data
        items_stock = await self.get_all_items_stock()
        await self.send(text_data=json.dumps({
            'type': 'initial_stock',
            'items': items_stock
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def stock_update(self, event):
        await self.send(text_data=json.dumps(event['data']))
    
    async def stock_reserve(self, event):
        await self.send(text_data=json.dumps(event['data']))
    
    async def menu_update(self, event):
        await self.send(text_data=json.dumps(event['data']))
    
    @database_sync_to_async
    def get_all_items_stock(self):
        items = MenuItem.objects.all().values('id', 'current_stock', 'is_available')
        return list(items)


class NotificationConsumer(AsyncWebsocketConsumer):
    """Handles real-time notifications for users"""
    async def connect(self):
        self.user = self.scope['user']
        self.session = self.scope['session']
        
        if self.user.is_authenticated:
            self.room_group_name = f'notifications_{self.user.id}'
        else:
            # Use session key for guests
            self.room_group_name = f'notifications_{self.session.session_key}'

        if self.room_group_name:
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )

        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name') and self.room_group_name:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def notification(self, event):
        await self.send(text_data=json.dumps(event['data']))


class CartReservationConsumer(AsyncWebsocketConsumer):
    """Handles cart reservation expiry and temporary stock blocking"""
    async def connect(self):
        self.room_group_name = 'cart_reservations'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def reservation_cleared(self, event):
        """Notify when a reservation expires and stock is freed"""
        await self.send(text_data=json.dumps(event['data']))
