"""
WebSocket utility functions for real-time updates and stock management
"""
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone
from datetime import timedelta
from .models import CartItem, MenuItem, Notification


def broadcast_stock_update(menu_item):
    """Broadcast stock update to all inventory consumers"""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        'inventory',
        {
            'type': 'stock_update',
            'data': {
                'type': 'stock_info',
                'item_id': menu_item.id,
                'name': menu_item.name,
                'new_stock': menu_item.current_stock,
                'is_available': menu_item.is_available and menu_item.current_stock > 0
            }
        }
    )


def broadcast_order_status_update(order_id, status, progress_percentage=None):
    """Broadcast order status update to tracking consumers"""
    channel_layer = get_channel_layer()
    
    data = {
        'type': 'order_status',
        'order_id': order_id,
        'status': status,
    }
    
    if progress_percentage is not None:
        data['progress_percentage'] = progress_percentage
    
    async_to_sync(channel_layer.group_send)(
        f'order_{order_id}',
        {
            'type': 'status_update',
            'data': data
        }
    )


def broadcast_notification(user_id=None, session_key=None, title="Notification", message="Message"):
    """Broadcast notification to user's notification consumer or session group"""
    channel_layer = get_channel_layer()
    
    group_name = None
    if user_id:
        group_name = f'notifications_{user_id}'
    elif session_key:
        group_name = f'notifications_{session_key}'
    
    if group_name:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'notification',
                'data': {
                    'type': 'new_notification',
                    'title': title,
                    'message': message,
                    'timestamp': timezone.now().isoformat(),
                }
            }
        )
    
    # Trigger background Push Notification
    try:
        from .models import PushSubscription
        subs = []
        if user_id:
            subs = PushSubscription.objects.filter(user_id=user_id)
        elif session_key:
            subs = PushSubscription.objects.filter(session_key=session_key)
            
        for sub in subs:
            send_push_notification(sub, title, message)
    except Exception as e:
        print(f"Push Notify Error: {e}")


def send_push_notification(subscription, title, message):
    """
    Send a background Web Push notification.
    Uses manual signing since pywebpush might not be available.
    """
    try:
        import requests
        import time
        import jwt # Assuming presence or using a simple implementation
        from django.conf import settings
        
        # This is a simplified Web Push implementation
        # For a full production system, pywebpush is recommended.
        # Here we provide the structure for the push trigger.
        
        payload = {
            "title": title,
            "message": message,
            "url": "/notifications/"
        }
        
        # Note: In a real environment, we'd sign with VAPID_PRIVATE_KEY here.
        # For this workspace, we'll log the push trigger.
        print(f"DEBUG: Sending Push to {subscription.endpoint}")
        print(f"DEBUG: Payload: {payload}")
        
        # Real logic would be:
        # headers = generate_vapid_headers(subscription.endpoint, settings.VAPID_PRIVATE_KEY)
        # requests.post(subscription.endpoint, json=payload, headers=headers)
        
    except Exception as e:
        print(f"Push Sender Error: {e}")


def set_cart_item_reservation(cart_item, reservation_minutes=1):
    """Set a temporary reservation on cart item (blocks stock for 1 minute)"""
    cart_item.reserved_at = timezone.now()
    cart_item.reservation_expires_at = timezone.now() + timedelta(minutes=reservation_minutes)
    cart_item.save()


def clear_expired_reservations():
    """Clear all expired cart reservations and return stock"""
    expired_items = CartItem.objects.filter(
        reservation_expires_at__isnull=False,
        reservation_expires_at__lt=timezone.now()
    )
    
    cleared_count = 0
    for cart_item in expired_items:
        # Return stock to menu item
        menu_item = cart_item.menu_item
        menu_item.current_stock += cart_item.quantity
        menu_item.save()
        
        # Delete the expired cart item
        cart_item.delete()
        cleared_count += 1
        
        # Broadcast the stock update
        broadcast_stock_update(menu_item)
    
    return cleared_count


def broadcast_menu_update(menu_item, action='updated'):
    """Broadcast menu item changes to kitchen and inventory consumers for instant updates"""
    channel_layer = get_channel_layer()
    
    data = {
        'type': 'menu_update',
        'action': action,  # 'added', 'updated', 'toggled'
        'item_id': menu_item.id,
        'name': menu_item.name,
        'price': str(menu_item.price),
        'category': menu_item.category,
        'is_veg': menu_item.is_veg,
        'is_available': menu_item.is_available,
        'current_stock': menu_item.current_stock,
        'ready_pool_stock': menu_item.ready_pool_stock,
        'image_url': menu_item.image.url if menu_item.image and menu_item.image.name else '',
    }
    
    # Notify kitchen dashboards
    async_to_sync(channel_layer.group_send)(
        'kitchen',
        {
            'type': 'menu_update',
            'data': data
        }
    )
    
    # Notify inventory/menu page consumers
    async_to_sync(channel_layer.group_send)(
        'inventory',
        {
            'type': 'menu_update',
            'data': data
        }
    )


def broadcast_progress_animation(order_id, start_percentage=10, end_percentage=90, duration_seconds=120):
    """
    Broadcast animated progress update to order tracker
    This tells the frontend to animate the progress bar slowly
    """
    channel_layer = get_channel_layer()
    
    async_to_sync(channel_layer.group_send)(
        f'order_{order_id}',
        {
            'type': 'progress_update',
            'data': {
                'type': 'progress_animation',
                'order_id': order_id,
                'start_percentage': start_percentage,
                'end_percentage': end_percentage,
                'duration_seconds': duration_seconds,
            }
        }
    )
