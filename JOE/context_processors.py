from .models import Notification, GuestProfile

def notifications_context(request):
    if not request.path.startswith('/admin/'):
        if request.user.is_authenticated:
            notifications = Notification.objects.filter(user=request.user)
            unread_count = notifications.filter(is_read=False).count()
        else:
            session_key = request.session.session_key
            if not session_key:
                request.session.create()
                session_key = request.session.session_key
            notifications = Notification.objects.filter(session_key=session_key, user=None)
            unread_count = notifications.filter(is_read=False).count()
        is_guest_active = False
        if not request.user.is_authenticated:
            if session_key and GuestProfile.objects.filter(session_key=session_key).exists():
                is_guest_active = True
                
        from django.conf import settings
        return {
            'notifications_list': notifications[:5], 
            'unread_notifications_count': unread_count,
            'is_guest_active': is_guest_active,
            'VAPID_PUBLIC_KEY': getattr(settings, 'VAPID_PUBLIC_KEY', ''),
        }
    return {}
