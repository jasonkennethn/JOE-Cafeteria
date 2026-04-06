/* ═══════════════════════════════════════════════════════════════
   JOE Cafeteria — Service Worker
   Handles background Push Notifications and Offline assets
   ═══════════════════════════════════════════════════════════════ */

self.addEventListener('push', function(event) {
    if (!event.data) return;
    
    const data = event.data.json();
    const title = data.title || "JOE Cafeteria Update";
    const options = {
        body: data.message || "You have a new update!",
        icon: '/static/img/logo-192.png',
        badge: '/static/img/badge-icon.png',
        data: { url: data.url || '/notifications/' },
        vibrate: [100, 50, 100],
        tag: 'order-update',
        renotify: true
    };

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    const urlToOpen = event.notification.data.url;

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
            for (var i = 0; i < windowClients.length; i++) {
                var client = windowClients[i];
                if (client.url === urlToOpen && 'focus' in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(urlToOpen);
            }
        })
    );
});
