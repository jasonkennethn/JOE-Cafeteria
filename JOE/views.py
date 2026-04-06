import json
import uuid
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from .models import MenuItem, Cart, CartItem, Order, OrderItem, User, Notification, GuestProfile, Feedback, Report
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .taglines import FOOD_TAGLINES


# ─── Utility ──────────────────────────────────────────────────────────

def get_cart(request):
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return cart
    else:
        session_key = request.session.session_key
        if not session_key:
            request.session.create()
            session_key = request.session.session_key
        cart, _ = Cart.objects.get_or_create(session_key=session_key, user=None)
        return cart


def get_cart_count(cart):
    if not cart:
        return 0
    return sum(item.quantity for item in cart.items.all())


def get_order_tagline(order_id):
    if not FOOD_TAGLINES:
        return "Freshly made and worth the wait."
    return FOOD_TAGLINES[order_id % len(FOOD_TAGLINES)]


def _notify_management(title, message):
    managers = User.objects.filter(
        role__in=['Cafeteria Manager', 'Cafeteria Owner'],
        is_active=True,
    )
    for manager in managers:
        Notification.objects.create(
            user=manager,
            title=title,
            message=message,
        )


# ─── Menu ─────────────────────────────────────────────────────────────

def menu(request):
    items = MenuItem.objects.all()

    is_veg_mode = False
    if request.user.is_authenticated:
        is_veg_mode = request.user.is_veg_mode
    else:
        is_veg_mode = request.session.get('is_veg_mode', False)

    if is_veg_mode:
        items = items.filter(is_veg=True)

    cart = get_cart(request)
    cart_count = get_cart_count(cart)

    # Pre-fetch cart quantities for menu items
    cart_items = {item.menu_item_id: item.quantity for item in cart.items.all()}

    # Get notification count (unfiltered for initial setup check)
    notif_count = 0
    if request.user.is_authenticated:
        notif_count = Notification.objects.filter(user=request.user).count()
    else:
        session_key = request.session.session_key
        if session_key:
            notif_count = Notification.objects.filter(session_key=session_key, user=None).count()

    # Serialize items for JS
    items_list = []
    for item in items:
        items_list.append({
            'id': item.id,
            'name': item.name,
            'description': item.description,
            'price': float(item.price),
            'image_url': item.image.url if item.image and hasattr(item.image, 'url') and item.image.name else '',
            'is_veg': item.is_veg,
            'category': item.category,
            'prep_time': item.prep_time_minutes,
            'stock': item.current_stock,
            'inventory_type': item.inventory_type,
        })
    items_json = json.dumps(items_list)

    cart_items_json = json.dumps({str(k): v for k, v in cart_items.items()})

    guest_name = None
    if not request.user.is_authenticated:
        session_key = request.session.session_key
        if session_key:
            guest_profile = GuestProfile.objects.filter(session_key=session_key).first()
            if guest_profile:
                guest_name = guest_profile.full_name

    # Get unique categories for filter
    categories = MenuItem.objects.filter(is_available=True).values_list('category', flat=True).distinct().order_by('category')

    context = {
        'items': items,
        'items_json': items_json,
        'cart': cart,
        'cart_count': cart_count,
        'cart_items_map': cart_items_json,
        'guest_name': guest_name,
        'categories': list(categories),
    }
    return render(request, 'menu.html', context)


def update_cart_api(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        item_id = data.get('item_id')
        action = data.get('action')
        target_qty = data.get('quantity')

        from django.utils import timezone
        from .websocket_utils import broadcast_stock_update, set_cart_item_reservation

        cart = get_cart(request)
        menu_item = get_object_or_404(MenuItem, id=item_id)
        cart_item, created = CartItem.objects.get_or_create(cart=cart, menu_item=menu_item)

        if action == 'add':
            if menu_item.current_stock > 0:
                menu_item.current_stock -= 1
                menu_item.save()
                
                if created:
                    cart_item.quantity = 1
                else:
                    cart_item.quantity += 1
                
                # Set 1-minute reservation on the cart item
                set_cart_item_reservation(cart_item, reservation_minutes=1)
                broadcast_stock_update(menu_item)
            else:
                return JsonResponse({'status': 'error', 'message': 'Out of stock'})
        elif action == 'remove':
            if not created and cart_item.quantity > 0:
                menu_item.current_stock += 1
                menu_item.save()
                
                if cart_item.quantity > 1:
                    cart_item.quantity -= 1
                    cart_item.save()
                else:
                    cart_item.delete()
                
                broadcast_stock_update(menu_item)
        elif action == 'set':
            try:
                target_qty = int(target_qty)
            except (TypeError, ValueError):
                target_qty = 0
                
            current_qty = cart_item.quantity if not created else 0
            
            if target_qty > current_qty:
                diff = target_qty - current_qty
                if menu_item.current_stock >= diff:
                    menu_item.current_stock -= diff
                    menu_item.save()
                    cart_item.quantity = target_qty
                    cart_item.save()
                    set_cart_item_reservation(cart_item, reservation_minutes=1)
                    broadcast_stock_update(menu_item)
                else:
                    if created:
                        cart_item.delete()
                    return JsonResponse({'status': 'error', 'message': 'Not enough stock'})
            elif target_qty < current_qty:
                diff = current_qty - target_qty
                menu_item.current_stock += diff
                menu_item.save()
                if target_qty > 0:
                    cart_item.quantity = target_qty
                    cart_item.save()
                    set_cart_item_reservation(cart_item, reservation_minutes=1)
                else:
                    cart_item.delete()
                broadcast_stock_update(menu_item)

        cart_count = get_cart_count(cart)
        item_quantity = cart_item.quantity if cart_item.id else 0
        return JsonResponse({'status': 'ok', 'quantity': item_quantity, 'cart_count': cart_count, 'cart_total': str(cart.total_price)})
    return JsonResponse({'status': 'invalid request'})


def cart_view(request):
    cart = get_cart(request)
    context = {
        'cart': cart,
        'cart_count': get_cart_count(cart)
    }
    return render(request, 'cart.html', context)


# ─── Checkout & Orders ────────────────────────────────────────────────

def checkout_view(request):
    is_guest = False
    if not request.user.is_authenticated:
        session_key = request.session.session_key
        if session_key and GuestProfile.objects.filter(session_key=session_key).exists():
            is_guest = True

    if not request.user.is_authenticated and not is_guest:
        request.session['next_after_login'] = '/cart/checkout/'
        return redirect('login')

    cart = get_cart(request)
    context = {
        'cart': cart,
        'cart_count': get_cart_count(cart),
    }
    return render(request, 'checkout.html', context)


def checkout_submit(request):
    if request.method == 'POST':
        user = request.user if request.user.is_authenticated else None
        guest_profile = None

        session_key = request.session.session_key
        if not user and session_key:
            guest_profile = GuestProfile.objects.filter(session_key=session_key).first()

        cart = None
        if user:
            cart = Cart.objects.filter(user=user).first()
        elif session_key:
            cart = Cart.objects.filter(session_key=session_key, user=None).first()

        if cart and cart.items.exists():
            from .websocket_utils import broadcast_order_status_update, broadcast_progress_animation
            
            secure_qr = str(uuid.uuid4())

            is_cashier = (user and user.role == 'Cashier')
            payment_type = request.POST.get('payment_method', 'Cash') if is_cashier else 'Online'

            order = Order.objects.create(
                user=user if not is_cashier else None,
                guest_profile=guest_profile if not is_cashier else None,
                placed_by_cashier=user if is_cashier else None,
                total_amount=cart.total_price,
                qr_code_id=secure_qr,
                payment_method=payment_type,
                status='Pending'
            )

            for item in cart.items.all():
                menu_item = item.menu_item
                # STORAGE AUTOMATION:
                # If enough is in storage, deduct and mark as Ready
                if menu_item.storage_stock >= item.quantity:
                    menu_item.storage_stock -= item.quantity
                    menu_item.save()
                    OrderItem.objects.create(
                        order=order,
                        menu_item=menu_item,
                        quantity=item.quantity,
                        price_at_time=menu_item.price,
                        status='Ready'
                    )
                elif menu_item.storage_stock > 0:
                    # Partial from storage, partial from kitchen
                    ready_qty = menu_item.storage_stock
                    pending_qty = item.quantity - ready_qty
                    
                    OrderItem.objects.create(
                        order=order,
                        menu_item=menu_item,
                        quantity=ready_qty,
                        price_at_time=menu_item.price,
                        status='Ready'
                    )
                    
                    menu_item.storage_stock = 0
                    menu_item.save()
                    
                    OrderItem.objects.create(
                        order=order,
                        menu_item=menu_item,
                        quantity=pending_qty,
                        price_at_time=menu_item.price,
                        status='Pending'
                    )
                else:
                    # All from kitchen
                    OrderItem.objects.create(
                        order=order,
                        menu_item=menu_item,
                        quantity=item.quantity,
                        price_at_time=menu_item.price,
                        status='Pending'
                    )

            # Flush the cart
            cart.items.all().delete()

            # Broadcast order creation and trigger progress animation
            try:
                from channels.layers import get_channel_layer
                from asgiref.sync import async_to_sync
                channel_layer = get_channel_layer()
                
                # Notify order status
                async_to_sync(channel_layer.group_send)(
                    f'order_{order.id}',
                    {
                        'type': 'status_update',
                        'data': {
                            'type': 'order_confirmed',
                            'order_id': order.id,
                            'status': 'Pending',
                            'total_amount': str(order.total_amount),
                        }
                    }
                )
                
                # Trigger progress animation (slow creep from 10% to 90% over 2 minutes)
                broadcast_progress_animation(order.id, start_percentage=10, end_percentage=90, duration_seconds=120)
                
                # Notify kitchen
                async_to_sync(channel_layer.group_send)(
                    'kitchen',
                    {
                        'type': 'order_update',
                        'data': {
                            'type': 'new_order',
                            'order_id': order.id,
                            'status': 'Pending',
                            'refresh': True
                        }
                    }
                )
            except Exception as e:
                print(f"WS Error in checkout: {e}")

            return redirect('order_success', order_id=order.id)

    return redirect('checkout')


def order_success_view(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    # Allow cashier who placed the order to view it
    if request.user.is_authenticated and request.user.role == 'Cashier':
        if order.placed_by_cashier == request.user:
            return render(request, 'order_success.html', {'order': order})

    if not request.user.is_authenticated:
        session_key = request.session.session_key
        if not order.guest_profile or order.guest_profile.session_key != session_key:
            return redirect('menu')
    elif order.user != request.user:
        # Also allow staff roles to see any order
        if request.user.role not in ['Cashier', 'Serving Desk', 'Kitchen Manager', 'Cafeteria Manager', 'Cafeteria Owner']:
            return redirect('menu')

    return render(request, 'order_success.html', {
        'order': order,
        'order_tagline': get_order_tagline(order.id),
        'order_created_iso': order.created_at.isoformat(),
    })


# ─── Auth ─────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        if request.user.role == 'Customer':
            return redirect('menu')
        return redirect('dashboard')

    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            try:
                user = User.objects.get(username=email)
            except User.DoesNotExist:
                user = None

        if user:
            auth_user = authenticate(request, username=user.username, password=password)
            if auth_user is not None:
                login(request, auth_user)

                # Merge session cart into user cart
                session_key = request.session.session_key
                if session_key:
                    session_cart = Cart.objects.filter(session_key=session_key, user=None).first()
                    if session_cart:
                        user_cart, _ = Cart.objects.get_or_create(user=auth_user)
                        for item in session_cart.items.all():
                            user_item, created = CartItem.objects.get_or_create(
                                cart=user_cart,
                                menu_item=item.menu_item,
                                defaults={'quantity': item.quantity}
                            )
                            if not created:
                                user_item.quantity += item.quantity
                                user_item.save()
                        session_cart.delete()

                next_url = request.session.get('next_after_login', None)
                if next_url:
                    del request.session['next_after_login']
                    return redirect(next_url)

                if auth_user.role == 'Customer':
                    return redirect('menu')
                return redirect('dashboard')

        return render(request, 'login.html', {'error': 'Invalid credentials'})

    return render(request, 'login.html')


def guest_login_post(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        phone_number = request.POST.get('phone_number')
        if not request.session.session_key:
            request.session.create()
        current_session = request.session.session_key

        existing_profile = GuestProfile.objects.filter(phone_number=phone_number).first()

        if existing_profile and existing_profile.session_key != current_session:
            old_session = existing_profile.session_key

            # Merge Carts
            old_cart = Cart.objects.filter(session_key=old_session, user=None).first()
            if old_cart:
                current_cart = Cart.objects.filter(session_key=current_session, user=None).first()
                if current_cart:
                    for item in old_cart.items.all():
                        new_item, created = CartItem.objects.get_or_create(
                            cart=current_cart,
                            menu_item=item.menu_item,
                            defaults={'quantity': item.quantity}
                        )
                        if not created:
                            new_item.quantity += item.quantity
                            new_item.save()
                    old_cart.delete()
                else:
                    old_cart.session_key = current_session
                    old_cart.save()

            # Merge Notifications
            Notification.objects.filter(session_key=old_session, user=None).update(session_key=current_session)

        GuestProfile.objects.update_or_create(
            phone_number=phone_number,
            defaults={'full_name': full_name, 'session_key': current_session}
        )
        return redirect('menu')
    return redirect('login')


# ─── Dashboard ────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    role = request.user.role

    if role == 'Customer':
        return redirect('menu')

    context = {
        'role': role,
    }

    if role == 'Kitchen Manager':
        context['pending_item_groups'] = OrderItem.objects.filter(
            status='Pending', order__is_disabled=False
        ).values('menu_item__id', 'menu_item__name').annotate(total_qty=Sum('quantity')).order_by('-total_qty')
        context['menu_items'] = MenuItem.objects.all().order_by('category', 'name')

    elif role == 'Serving Desk':
        context['orders'] = Order.objects.filter(
            items__status='Ready', is_disabled=False
        ).distinct().order_by('created_at')
        context['wait_time_requests'] = Order.objects.filter(
            extra_time_status='Pending', is_disabled=False
        ).order_by('created_at')

    elif role == 'Cashier':
        context['counter_orders'] = Order.objects.all().order_by('-created_at')[:50]

    elif role in ['Cafeteria Manager', 'Cafeteria Owner']:
        today = timezone.now().date()
        all_orders = Order.objects.filter(is_disabled=False)
        today_orders = all_orders.filter(created_at__date=today)
        
        from .models import SystemSettings
        context['default_wait_time'] = SystemSettings.load().default_pickup_wait_time_minutes

        context['total_sales'] = all_orders.aggregate(total=Sum('total_amount'))['total'] or 0
        context['today_sales'] = today_orders.aggregate(total=Sum('total_amount'))['total'] or 0
        context['total_orders'] = all_orders.count()
        context['today_orders'] = today_orders.count()
        context['pending_orders'] = all_orders.filter(status='Pending').count()
        context['completed_orders'] = all_orders.filter(status='Completed').count()
        context['active_staff'] = User.objects.filter(
            role__in=['Cashier', 'Kitchen Manager', 'Serving Desk'], is_active=True
        ).count()

        # Popular items
        context['popular_items'] = OrderItem.objects.values(
            'menu_item__name'
        ).annotate(
            total_sold=Sum('quantity')
        ).order_by('-total_sold')[:8]

        # Recent orders
        context['recent_orders'] = all_orders.order_by('-created_at')[:10]

        # Payment split
        context['payment_split'] = all_orders.values('payment_method').annotate(
            count=Count('id'),
            total=Sum('total_amount')
        ).order_by('-total')

        # Disabled/disputed orders
        context['disputed_orders'] = Order.objects.filter(is_disabled=True).count()

    return render(request, 'dashboard.html', context)


# ─── Item Status Updates ──────────────────────────────────────────────

@login_required
def update_item_status(request):
    if request.method == 'POST':
        item_id = request.POST.get('menu_item_id')
        specific_order_item_id = request.POST.get('order_item_id')
        new_status = request.POST.get('status')

        # Validate permissions
        if request.user.role in ['Customer']:
            return redirect('menu')

        if item_id:  # Kitchen Manager marking a huge batch as cooked!
            items = OrderItem.objects.filter(menu_item_id=item_id, status='Pending', order__is_disabled=False)

            from .websocket_utils import broadcast_notification
            for item in items:
                order = item.order
                title = "Item Ready! 🥟"
                msg = f"Your {item.menu_item.name} is ready for pickup! Please head to the Serving Desk."
                
                # Save to DB
                Notification.objects.create(
                    user=order.user, 
                    session_key=order.guest_profile.session_key if order.guest_profile else None,
                    title=title, 
                    message=msg
                )
                
                # Broadcast Real-time + Push
                broadcast_notification(
                    user_id=order.user.id if order.user else None,
                    session_key=order.guest_profile.session_key if order.guest_profile else None,
                    title=title,
                    message=msg
                )

            # Commit block update
            items.update(status=new_status)
            
            # Start Countdown for any orders that just became 'Ready'
            if new_status == 'Ready':
                from django.utils import timezone
                from .models import Order, SystemSettings
                # Get the orders affected
                order_ids = set()
                # we need to query items again because they were updated in bulk
                updated_items = OrderItem.objects.filter(menu_item_id=item_id, status='Ready', order__is_disabled=False)
                for ui in updated_items:
                    order_ids.add(ui.order_id)
                settings = SystemSettings.load()
                for oid in order_ids:
                    o = Order.objects.get(id=oid)
                    if not o.ready_at:
                        o.ready_at = timezone.now()
                        o.pickup_deadline = o.ready_at + timezone.timedelta(minutes=settings.default_pickup_wait_time_minutes)
                        o.save()
                        
                channel_layer = get_channel_layer()
                for oid in order_ids:
                    async_to_sync(channel_layer.group_send)(
                        f'order_{oid}',
                        {
                            'type': 'status_update',
                            'data': {'type': 'refresh'}
                        }
                    )
                async_to_sync(channel_layer.group_send)(
                    'kitchen', {'type': 'stock_update', 'data': {'type': 'refresh', 'refresh': True}}
                )
                async_to_sync(channel_layer.group_send)(
                    'serving', {'type': 'serving_update', 'data': {'type': 'refresh', 'refresh': True}}
                )

        elif specific_order_item_id:  # Serving Desk handing a plate over to the Customer
            try:
                item = OrderItem.objects.get(id=specific_order_item_id)
                order = item.order

                # Serve only when the specific order item is marked ready.
                if item.status == 'Ready':
                    item.status = 'Served'
                    item.save()

                    # Close out Order logically if all items are fully gone
                    if not order.items.exclude(status='Served').exists():
                        order.status = 'Completed'
                        order.save()
                        
                        from .websocket_utils import broadcast_notification
                        title = "Order Complete! ✅"
                        msg = f"Your order #{order.id} has been fully served. Thank you!"
                        
                        Notification.objects.create(
                            user=order.user,
                            session_key=order.guest_profile.session_key if order.guest_profile else None,
                            title=title,
                            message=msg
                        )
                        
                        broadcast_notification(
                            user_id=order.user.id if order.user else None,
                            session_key=order.guest_profile.session_key if order.guest_profile else None,
                            title=title,
                            message=msg
                        )
                    elif order.items.filter(status='Served').exists():
                        order.status = 'Partial'
                        order.save()
                    
                    # BROADCAST REAL-TIME: Ensure customer screen updates instantly!
                    try:
                        from channels.layers import get_channel_layer
                        from asgiref.sync import async_to_sync
                        channel_layer = get_channel_layer()
                        async_to_sync(channel_layer.group_send)(
                            f'order_{order.id}',
                            {'type': 'status_update', 'data': {'type': 'refresh'}}
                        )
                        async_to_sync(channel_layer.group_send)(
                            'serving', {'type': 'serving_update', 'data': {'type': 'refresh', 'refresh': True}}
                        )
                        async_to_sync(channel_layer.group_send)(
                            'kitchen', {'type': 'stock_update', 'data': {'type': 'refresh', 'refresh': True}}
                        )
                    except Exception as e:
                        print(f"WS Error in handover: {e}")

            except OrderItem.DoesNotExist:
                pass

    return redirect('dashboard')



@login_required
def toggle_order_dispute(request, order_id):
    if request.user.role != 'Cashier' and request.user.role not in ['Cafeteria Manager', 'Cafeteria Owner']:
        return redirect('menu')
    order = get_object_or_404(Order, id=order_id)
    order.is_disabled = not order.is_disabled
    order.save()
    return redirect('dashboard')


# ─── QR Scan API for Serving Desk ────────────────────────────────────

@login_required
def scan_qr_api(request):
    """Serving Desk scans a QR code to pull up an order for handoff."""
    if request.user.role not in ['Serving Desk', 'Cashier', 'Cafeteria Manager', 'Cafeteria Owner']:
        return JsonResponse({'status': 'unauthorized'}, status=403)

    if request.method == 'POST':
        data = json.loads(request.body)
        qr_id = data.get('qr_code_id', '').strip()

        if not qr_id:
            return JsonResponse({'status': 'error', 'message': 'No QR code provided'})

        try:
            order = Order.objects.get(qr_code_id=qr_id)
        except Order.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Invalid QR code. No order found.'})

        if order.is_disabled:
            return JsonResponse({'status': 'error', 'message': 'This order is currently disabled due to a dispute.'})

        if order.status == 'Completed':
            return JsonResponse({'status': 'error', 'message': 'This order has already been fully served. QR is no longer valid.'})

        items_data = []
        for item in order.items.all():
            items_data.append({
                'id': item.id,
                'name': item.menu_item.name,
                'quantity': item.quantity,
                'status': item.status,
                'price': str(item.price_at_time),
            })

        customer_name = 'Counter Walk-up'
        if order.user:
            customer_name = order.user.get_full_name() or order.user.username
        elif order.guest_profile:
            customer_name = order.guest_profile.full_name

        return JsonResponse({
            'status': 'ok',
            'order': {
                'id': order.id,
                'customer': customer_name,
                'total': str(order.total_amount),
                'payment_method': order.payment_method,
                'order_status': order.status,
                'created_at': order.created_at.strftime('%I:%M %p'),
                'qr_code_id': order.qr_code_id,
                'items': items_data,
            }
        })

    return JsonResponse({'status': 'invalid'})


@login_required
def serve_item_api(request):
    """AJAX endpoint to mark individual item as served without page reload."""
    if request.method == 'POST':
        if request.user.role not in ['Serving Desk', 'Cafeteria Manager', 'Cafeteria Owner']:
            return JsonResponse({'status': 'unauthorized'}, status=403)

        data = json.loads(request.body)
        order_item_id = data.get('order_item_id')

        try:
            item = OrderItem.objects.get(id=order_item_id)
            item.status = 'Served'
            item.save()

            order = item.order
            remaining = order.items.exclude(status='Served').count()

            if remaining == 0:
                order.status = 'Completed'
                order.save()
                from .websocket_utils import broadcast_notification
                title = "Order Complete! ✅"
                msg = f"Your order #{order.id} has been fully served. Thank you for choosing JOE!"
                
                Notification.objects.create(
                    user=order.user,
                    session_key=order.guest_profile.session_key if order.guest_profile else None,
                    title=title,
                    message=msg
                )
                
                broadcast_notification(
                    user_id=order.user.id if order.user else None,
                    session_key=order.guest_profile.session_key if order.guest_profile else None,
                    title=title,
                    message=msg
                )
            else:
                order.status = 'Partial'
                order.save()

            return JsonResponse({
                'status': 'ok',
                'item_status': 'Served',
                'remaining': remaining,
                'order_status': order.status,
            })
        except OrderItem.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Item not found'})

    return JsonResponse({'status': 'invalid'})


# ─── My Orders ────────────────────────────────────────────────────────

def my_orders_view(request):
    orders = Order.objects.none()

    if request.user.is_authenticated:
        orders = Order.objects.filter(user=request.user).order_by('-created_at')
    else:
        session_key = request.session.session_key
        if session_key:
            guest_profile = GuestProfile.objects.filter(session_key=session_key).first()
            if guest_profile:
                orders = Order.objects.filter(guest_profile=guest_profile).order_by('-created_at')

    if not request.user.is_authenticated and not orders.exists():
        return redirect('login')

    for order in orders:
        order.tagline = get_order_tagline(order.id)
    return render(request, 'my_orders.html', {'orders': orders})


# ─── Menu Management ─────────────────────────────────────────────────

@login_required
def manage_menu_view(request):
    if request.user.role not in ['Cafeteria Manager', 'Cafeteria Owner', 'Kitchen Manager']:
        return redirect('menu')

    items = MenuItem.objects.all().order_by('category', 'name')
    categories = MenuItem.CATEGORY_CHOICES

    context = {
        'menu_items': items,
        'categories': categories,
        'role': request.user.role,
    }
    return render(request, 'manage_menu.html', context)


@login_required
def add_edit_menu_item(request):
    if request.user.role not in ['Cafeteria Manager', 'Cafeteria Owner', 'Kitchen Manager']:
        return redirect('menu')

    if request.method == 'POST':
        item_id = request.POST.get('item_id')
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        price = request.POST.get('price')
        category = request.POST.get('category', 'Snacks')
        is_veg = request.POST.get('is_veg') == 'true'
        prep_time = request.POST.get('prep_time_minutes', 0)
        inventory_type = request.POST.get('inventory_type', 'continuous')
        current_stock = request.POST.get('current_stock', 100)
        storage_stock = request.POST.get('storage_stock', 0)
        is_available = request.POST.get('is_available') == 'true'

        if item_id:
            item = get_object_or_404(MenuItem, id=item_id)
        else:
            item = MenuItem()

        item.name = name
        item.description = description
        item.price = price
        item.category = category
        item.is_veg = is_veg
        item.prep_time_minutes = int(prep_time)
        item.inventory_type = inventory_type
        item.current_stock = int(current_stock)
        item.storage_stock = int(storage_stock)
        item.is_available = is_available

        if request.FILES.get('image'):
            item.image = request.FILES['image']

        item.save()

        # Broadcast menu update via WebSocket for instant reflection
        try:
            from .websocket_utils import broadcast_menu_update
            action = 'added' if not item_id else 'updated'
            broadcast_menu_update(item, action=action)
        except Exception as e:
            print(f"WS broadcast error in add_edit_menu_item: {e}")

        return JsonResponse({'status': 'ok', 'item_id': item.id})

    return JsonResponse({'status': 'invalid'})


@login_required
def toggle_menu_item_api(request):
    if request.method == 'POST':
        if request.user.role not in ['Cafeteria Manager', 'Cafeteria Owner', 'Kitchen Manager']:
            return JsonResponse({'status': 'unauthorized'}, status=403)

        data = json.loads(request.body)
        item_id = data.get('item_id')
        field = data.get('field')  # 'availability' or 'stock'
        value = data.get('value')

        item = get_object_or_404(MenuItem, id=item_id)

        if field == 'availability':
            item.is_available = value
        elif field == 'stock':
            item.current_stock = int(value)

        item.save()

        # Broadcast menu update via WebSocket
        try:
            from .websocket_utils import broadcast_menu_update
            broadcast_menu_update(item, action='toggled')
        except Exception as e:
            print(f"WS broadcast error in toggle_menu_item_api: {e}")

        return JsonResponse({'status': 'ok'})

    return JsonResponse({'status': 'invalid'})


# ─── Profile & Settings ──────────────────────────────────────────────

def profile_view(request):
    guest_profile = None
    if not request.user.is_authenticated:
        session_key = request.session.session_key
        if session_key:
            guest_profile = GuestProfile.objects.filter(session_key=session_key).first()

        if not guest_profile:
            return redirect('login')

    user_role = request.user.role if request.user.is_authenticated else 'Guest'
    return render(request, 'profile.html', {'guest_profile': guest_profile, 'user_role': user_role})


def about_us_view(request):
    developer_details = {
        'name': 'JOE Cafeteria Development Team',
        'focus': 'Campus-ready product engineering',
        'mission': 'Deliver smooth dining operations for students, staff, and service teams.',
    }
    return render(request, 'about_us.html', {'developer_details': developer_details})


def privacy_policy_view(request):
    return render(request, 'privacy_policy.html')


def feedback_view(request):
    if request.method == 'POST':
        message = request.POST.get('message', '').strip()
        if message:
            session_key = request.session.session_key
            if not session_key:
                request.session.create()
                session_key = request.session.session_key

            feedback = Feedback.objects.create(
                user=request.user if request.user.is_authenticated else None,
                session_key=None if request.user.is_authenticated else session_key,
                message=message,
            )

            identity = 'Guest user'
            if request.user.is_authenticated:
                identity = request.user.get_full_name() or request.user.username

            _notify_management(
                title='New Feedback Submitted',
                message=f'Feedback #{feedback.id} from {identity}: {message[:120]}',
            )

            return redirect('feedback')

    feedback_items = Feedback.objects.none()
    if request.user.is_authenticated:
        feedback_items = Feedback.objects.filter(user=request.user)
    else:
        session_key = request.session.session_key
        if session_key:
            feedback_items = Feedback.objects.filter(session_key=session_key, user=None)

    return render(request, 'feedback.html', {'feedback_items': feedback_items})


def report_view(request):
    # Customer side only: guest users and customer accounts (including Google sign-in).
    if request.user.is_authenticated and request.user.role != 'Customer':
        return redirect('profile')

    guest_profile = None
    if not request.user.is_authenticated:
        session_key = request.session.session_key
        if session_key:
            guest_profile = GuestProfile.objects.filter(session_key=session_key).first()
        if not guest_profile:
            return redirect('login')

    if request.method == 'POST':
        subject = request.POST.get('subject', '').strip()
        description = request.POST.get('description', '').strip()
        if subject and description:
            report = Report.objects.create(
                user=request.user if request.user.is_authenticated else None,
                guest_profile=guest_profile,
                subject=subject,
                description=description,
            )

            reporter = 'Guest customer'
            if request.user.is_authenticated:
                reporter = request.user.get_full_name() or request.user.username
            elif guest_profile:
                reporter = guest_profile.full_name

            _notify_management(
                title='New Customer Report',
                message=f'Report #{report.id} from {reporter}: {subject}',
            )

            return redirect('report')

    if request.user.is_authenticated:
        reports = Report.objects.filter(user=request.user)
    else:
        reports = Report.objects.filter(guest_profile=guest_profile)

    return render(request, 'report.html', {'reports': reports})


def user_logout(request):
    if not request.user.is_authenticated:
        request.session.flush()
    else:
        logout(request)
    return redirect('menu')


def toggle_theme_or_veg(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        field = data.get('field')
        value = data.get('value')

        if request.user.is_authenticated:
            if field == 'theme':
                request.user.dark_theme = value
            elif field == 'veg_mode':
                request.user.is_veg_mode = value
            request.user.save()
        else:
            if field == 'theme':
                request.session['dark_theme'] = value
            elif field == 'veg_mode':
                request.session['is_veg_mode'] = value
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'invalid'})


# ─── Notifications ────────────────────────────────────────────────────

def notifications_view(request):
    if request.user.is_authenticated:
        notifications = Notification.objects.filter(user=request.user)
    else:
        session_key = request.session.session_key
        notifications = Notification.objects.filter(session_key=session_key, user=None)

    return render(request, 'notifications.html', {'notifications': notifications})


def notification_action_api(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        action = data.get('action')
        notif_id = data.get('notif_id')

        if request.user.is_authenticated:
            base_qs = Notification.objects.filter(user=request.user)
        else:
            session_key = request.session.session_key
            base_qs = Notification.objects.filter(session_key=session_key, user=None)

        if action == 'mark_read':
            notif = get_object_or_404(base_qs, id=notif_id)
            notif.is_read = True
            notif.save()
        elif action == 'read_all':
            base_qs.update(is_read=True)
        elif action == 'clear':
            notif = get_object_or_404(base_qs, id=notif_id)
            notif.delete()
        elif action == 'clear_all':
            base_qs.delete()

        return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'invalid'})

# ─── New Wait Time & Reallocation Logic ───────────────────────────────

def _process_expired_orders():
    from django.utils import timezone
    from .models import Order, OrderItem, SystemSettings
    
    grace_deadline = timezone.now() - timezone.timedelta(minutes=1)
    expired_orders = Order.objects.filter(
        pickup_deadline__lt=grace_deadline,
        is_disabled=False
    ).exclude(extra_time_status='Pending')
    
    for order in expired_orders:
        ready_items = order.items.filter(status='Ready')
        if not ready_items.exists():
            # Nothing to re-assign
            order.pickup_deadline = None
            order.ready_at = None
            order.save()
            continue
            
        for r_item in ready_items:
            next_order_item = OrderItem.objects.filter(
                menu_item=r_item.menu_item,
                status='Pending',
                order__is_disabled=False
            ).order_by('order__created_at').first()
            
            if next_order_item:
                # Reassign
                next_order_item.status = 'Ready'
                next_order_item.save()
                
                new_order = next_order_item.order
                if not new_order.ready_at:
                    wait_time = SystemSettings.load().default_pickup_wait_time_minutes
                    new_order.ready_at = timezone.now()
                    new_order.pickup_deadline = new_order.ready_at + timezone.timedelta(minutes=wait_time)
                    new_order.save()
                
                # Turn original back to pending
                r_item.status = 'Pending'
                r_item.save()
                
        # Ensure cleanup
        order.ready_at = None
        order.pickup_deadline = None
        order.extra_time_requested = 0
        order.extra_time_status = 'None'
        order.save()

def _process_expired_cart_reservations():
    from django.utils import timezone
    from .models import CartItem, MenuItem
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    
    layer = get_channel_layer()
    expiry_time = timezone.now() - timezone.timedelta(minutes=1)
    expired_items = CartItem.objects.filter(reserved_at__lt=expiry_time)
    
    for item in expired_items:
        m_item = item.menu_item
        m_item.current_stock += item.quantity
        m_item.save()
        
        # Broadcast to all users
        async_to_sync(layer.group_send)(
            'inventory',
            {
                'type': 'stock_update',
                'data': {
                    'type': 'stock_info',
                    'item_id': m_item.id,
                    'new_stock': m_item.current_stock,
                    'is_available': m_item.is_available and m_item.current_stock > 0
                }
            }
        )
        item.delete()

@login_required
def update_kitchen_stock(request):
    from .models import MenuItem
    if request.user.role != 'Kitchen Manager':
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'})
    import json
    data = json.loads(request.body)
    item = MenuItem.objects.get(id=data['item_id'])
    item.current_stock = int(data['stock'])
    if 'storage_stock' in data:
        item.storage_stock = int(data['storage_stock'])
    item.is_available = data['is_available']
    item.save()
    
    # Broadcast to kitchen and inventory for instant updates
    try:
        from .websocket_utils import broadcast_menu_update, broadcast_stock_update
        broadcast_menu_update(item, action='updated')
        broadcast_stock_update(item)
    except Exception as e:
        print(f"WS broadcast error in update_kitchen_stock: {e}")
    
    return JsonResponse({'status': 'ok'})

@login_required
def update_system_settings(request):
    from .models import SystemSettings
    if request.user.role not in ['Cafeteria Manager', 'Cafeteria Owner']:
        return redirect('dashboard')
    
    new_time = request.POST.get('wait_time')
    if new_time:
        settings = SystemSettings.load()
        settings.default_pickup_wait_time_minutes = int(new_time)
        settings.save()
    return redirect('dashboard')

def get_order_status(request, order_id):
    from django.utils import timezone
    from .models import Order
    try:
        order = Order.objects.get(id=order_id)
        
        # trigger processing here optionally so background works smoothly
        _process_expired_orders()
        _process_expired_cart_reservations()
        
        # Re-fetch just in case
        order = Order.objects.get(id=order_id)
        
        all_items = order.items.all()
        ready_items = all_items.filter(status='Ready').count()
        served_items = all_items.filter(status='Served').count()
        pending_items = all_items.filter(status='Pending').count()
        
        global_status = 'In Kitchen'
        if ready_items > 0:
            global_status = 'Ready for Pickup'
        if pending_items == 0 and ready_items == 0 and served_items > 0:
            global_status = 'Completed'
            
        deadline = order.pickup_deadline.isoformat() if order.pickup_deadline else None
        
        return JsonResponse({
            'status': 'ok',
            'global_status': global_status,
            'ready_count': ready_items,
            'served_count': served_items,
            'pending_count': pending_items,
            'deadline': deadline,
            'extra_time_status': order.extra_time_status,
            'extra_time_requested': order.extra_time_requested
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

def request_extra_time(request, order_id):
    from .models import Order
    import json
    try:
        order = Order.objects.get(id=order_id)
        data = json.loads(request.body)
        mins = int(data.get('minutes', 5))
        
        if order.extra_time_status in ['None', 'Rejected', None, '']:
            order.extra_time_requested = mins
            order.extra_time_status = 'Pending'
            order.save()
            
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                'serving', {'type': 'serving_update', 'data': {'type': 'refresh'}}
            )
            
            return JsonResponse({'status': 'ok'})
        return JsonResponse({'status': 'error', 'message': 'Already requested'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@login_required
def handle_time_request(request, order_id):
    from django.utils import timezone
    from .models import Order
    if request.user.role != 'Serving Desk':
        return redirect('dashboard')
        
    action = request.POST.get('action') # 'accept' or 'reject'
    order = Order.objects.get(id=order_id)
    
    from .websocket_utils import broadcast_notification
    title = f"Wait Time Update — Order #{order.id}"
    msg = ""
    
    if action == 'accept' and order.extra_time_status == 'Pending':
        order.extra_time_status = 'Accepted'
        msg = f"Your request for +{order.extra_time_requested} mins has been accepted! New deadline set."
        if order.pickup_deadline:
            if order.pickup_deadline < timezone.now():
                order.pickup_deadline = timezone.now() + timezone.timedelta(minutes=order.extra_time_requested)
            else:
                order.pickup_deadline += timezone.timedelta(minutes=order.extra_time_requested)
        order.save()
    elif action == 'reject' and order.extra_time_status == 'Pending':
        order.extra_time_status = 'Rejected'
        msg = "Your request for extra wait time was rejected. Please arrive as soon as possible."
        order.save()
        
    if msg:
        Notification.objects.create(
            user=order.user,
            session_key=order.guest_profile.session_key if order.guest_profile else None,
            title=title,
            message=msg
        )
        broadcast_notification(
            user_id=order.user.id if order.user else None,
            session_key=order.guest_profile.session_key if order.guest_profile else None,
            title=title,
            message=msg
        )
        
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'order_{order.id}', {'type': 'status_update', 'data': {'type': 'refresh'}}
    )
        
    return redirect('dashboard')


# ─── Error Handlers ───────────────────────────────────────────────────

def error_404_view(request, exception):
    return render(request, '404.html', status=404)

def error_403_view(request, exception):
    return render(request, '403.html', status=403)

def error_500_view(request):
    return render(request, '500.html', status=500)

@login_required
def save_push_subscription(request):
    if request.method == 'POST':
        import json
        from .models import PushSubscription
        data = json.loads(request.body)
        
        # Determine user/session context
        user = request.user if request.user.is_authenticated else None
        session_key = request.session.session_key if not user else None
        
        PushSubscription.objects.update_or_create(
            endpoint=data.get('endpoint'),
            defaults={
                'user': user,
                'session_key': session_key,
                'p256dh': data.get('p256dh'),
                'auth': data.get('auth')
            }
        )
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'invalid'}, status=400)
