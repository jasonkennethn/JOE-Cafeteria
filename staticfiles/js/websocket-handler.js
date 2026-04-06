/**
 * WebSocket Handler for Real-time Updates
 * Manages all WebSocket connections for menu, cart, and order tracking
 */

class WebSocketManager {
    constructor() {
        this.protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        this.host = window.location.host;
        this.sockets = {};
        this.stockUpdates = {};
        this.eventHandlers = {};
    }

    /**
     * Initialize inventory WebSocket for real-time stock updates
     */
    initInventorySocket() {
        const socketId = 'inventory';
        if (this.sockets[socketId]) {
            this.sockets[socketId].close();
        }

        const url = `${this.protocol}://${this.host}/ws/inventory/`;
        const socket = new WebSocket(url);

        socket.onopen = (e) => {
            console.log('✓ Inventory WebSocket connected');
            this.updateSocketStatus(socketId, 'connected');
        };

        socket.onmessage = (e) => {
            const message = JSON.parse(e.data);
            this.handleInventoryMessage(message);
        };

        socket.onerror = (error) => {
            console.error('✗ Inventory WebSocket error:', error);
            this.updateSocketStatus(socketId, 'error');
        };

        socket.onclose = (e) => {
            console.log('✗ Inventory WebSocket closed');
            this.updateSocketStatus(socketId, 'closed');
            // Attempt reconnect after 5 seconds
            setTimeout(() => this.initInventorySocket(), 5000);
        };

        this.sockets[socketId] = socket;
    }

    /**
     * Handle inventory messages
     */
    handleInventoryMessage(message) {
        if (message.type === 'initial_stock') {
            // Initialize stock from server
            message.items.forEach(item => {
                this.updateStockDisplay(item.id, item.current_stock, item.is_available);
            });
        } else if (message.type === 'stock_info') {
            // Real-time stock update
            this.updateStockDisplay(
                message.item_id,
                message.new_stock,
                message.is_available,
                message.name
            );
        } else if (message.type === 'menu_update') {
            // Menu item was added, edited, or toggled from Manage Menu / Kitchen
            console.log(`🍽️ Menu update: ${message.action} – ${message.name}`);
            
            // Update stock display if item exists on page
            this.updateStockDisplay(
                message.item_id,
                message.current_stock,
                message.is_available,
                message.name
            );
            
            // For newly added items or major edits, reload menu content
            if (message.action === 'added') {
                // New item added — reload the page to show it
                if (document.querySelector('[data-id]')) {
                    setTimeout(() => window.location.reload(), 500);
                }
            }
        }
    }

    /**
     * Update stock display on menu page
     */
    updateStockDisplay(itemId, stockCount, isAvailable, itemName = null) {
        const quantityElement = document.getElementById(`stock-qty-${itemId}`);
        const labelElement = document.getElementById(`stock-label-${itemId}`);
        const cardElement = document.querySelector(`[data-id="${itemId}"]`);
        const overlayElement = document.getElementById(`unavailable-overlay-${itemId}`);

        if (!quantityElement || !labelElement || !cardElement || !overlayElement) {
            return; // Elements not on current page
        }

        // Update quantity
        quantityElement.textContent = stockCount;

        // Update availability
        if (isAvailable && stockCount > 0) {
            // Show ready status
            labelElement.className = 'inline-flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider bg-green-50 text-green-600 px-2 py-0.5 rounded-full border border-green-100 dark:bg-green-500/10 dark:border-green-500/20';
            labelElement.innerHTML = `<i class="bi bi-check2-circle"></i> Ready · ${stockCount} left`;
            cardElement.classList.remove('item-frozen');
            overlayElement.classList.add('hidden');
        } else {
            // Show unavailable status
            labelElement.className = 'inline-flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full dark:bg-gray-700 dark:text-gray-400';
            labelElement.innerHTML = '<i class="bi bi-x-circle"></i> Unavailable';
            cardElement.classList.add('item-frozen');
            overlayElement.classList.remove('hidden');
        }

        // Log update
        console.log(`📦 ${itemName || `Item ${itemId}`}: ${stockCount} left (${isAvailable ? 'Available' : 'Unavailable'})`);
    }

    /**
     * Initialize order tracking WebSocket
     */
    initOrderSocket(orderId) {
        const socketId = `order_${orderId}`;
        if (this.sockets[socketId]) {
            this.sockets[socketId].close();
        }

        const url = `${this.protocol}://${this.host}/ws/order/${orderId}/`;
        const socket = new WebSocket(url);

        socket.onopen = (e) => {
            console.log(`✓ Order ${orderId} WebSocket connected`);
            this.updateSocketStatus(socketId, 'connected');
        };

        socket.onmessage = (e) => {
            const message = JSON.parse(e.data);
            this.handleOrderMessage(orderId, message);
        };

        socket.onerror = (error) => {
            console.error(`✗ Order ${orderId} WebSocket error:`, error);
            this.updateSocketStatus(socketId, 'error');
        };

        socket.onclose = (e) => {
            console.log(`✗ Order ${orderId} WebSocket closed`);
            this.updateSocketStatus(socketId, 'closed');
        };

        this.sockets[socketId] = socket;
    }

    /**
     * Handle order messages and update UI
     */
    handleOrderMessage(orderId, message) {
        if (message.type === 'initial_status' || message.type === 'order_status') {
            this.updateOrderStatus(orderId, message.data);
        } else if (message.type === 'progress_animation') {
            this.startProgressAnimation(
                orderId,
                message.data.start_percentage,
                message.data.end_percentage,
                message.data.duration_seconds
            );
        }
    }

    /**
     * Update order status display
     */
    updateOrderStatus(orderId, orderData) {
        const statusElement = document.getElementById('tracker-status-text');
        const subElement = document.getElementById('tracker-sub');

        if (!statusElement || !subElement) return;

        const statusMap = {
            'Pending': { text: 'Preparing Order...', icon: '⏳', color: 'text-orange-500' },
            'Partial': { text: 'Partially Ready', icon: '⚡', color: 'text-blue-500' },
            'Completed': { text: 'Ready for Pickup!', icon: '✅', color: 'text-green-500' },
        };

        const status = statusMap[orderData.status] || { text: orderData.status, icon: '📋', color: 'text-gray-500' };

        statusElement.innerHTML = `${status.icon} ${status.text}`;
        statusElement.className = `text-2xl font-black ${status.color} mb-2`;

        if (orderData.status === 'Completed') {
            subElement.textContent = 'Your order is ready! Please come to the counter.';
            this.animateCompletion();
        } else if (orderData.status === 'Partial') {
            subElement.textContent = 'Some items are ready, others still being prepared.';
        } else {
            subElement.textContent = 'Your food is being prepared with care.';
        }

        console.log(`🔄 Order ${orderId} status: ${orderData.status}`);
    }

    /**
     * Animate progress bar slowly (creeping effect)
     * Simulates work being done without real updates
     */
    startProgressAnimation(orderId, startPercentage = 10, endPercentage = 90, durationSeconds = 120) {
        const progressBar = document.getElementById('progress-bar');
        if (!progressBar) return;

        // Set initial width and remove any existing animation class
        progressBar.style.width = startPercentage + '%';
        progressBar.classList.remove('progress-creep');
        progressBar.offsetHeight; // Trigger reflow to restart animation
        progressBar.classList.add('progress-creep');

        // Smooth transition
        progressBar.style.transition = `width ${durationSeconds}s cubic-bezier(0.4, 0, 0.2, 1)`;

        // After a small delay, start the animation
        setTimeout(() => {
            progressBar.style.width = endPercentage + '%';
        }, 100);

        console.log(`🎬 Progress animation started: ${startPercentage}% → ${endPercentage}% over ${durationSeconds}s`);
    }

    /**
     * Animate completion state (pulse effect)
     */
    animateCompletion() {
        const progressBar = document.getElementById('progress-bar');
        const statusElement = document.getElementById('tracker-status-text');

        if (progressBar) {
            progressBar.style.width = '100%';
            progressBar.style.background = 'linear-gradient(90deg, #10b981, #34d399)';
            progressBar.classList.remove('progress-creep');
            progressBar.style.animation = 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite';
        }

        if (statusElement) {
            statusElement.style.animation = 'pulse 1s cubic-bezier(0.4, 0, 0.6, 1) infinite';
        }
    }

    /**
     * Update socket status badge (for debugging)
     */
    updateSocketStatus(socketId, status) {
        const statusElement = document.getElementById(`socket-status-${socketId}`);
        if (statusElement) {
            statusElement.textContent = status.toUpperCase();
            statusElement.className = `text-xs font-bold ${
                status === 'connected' ? 'text-green-600 bg-green-100' :
                status === 'error' ? 'text-red-600 bg-red-100' :
                'text-gray-600 bg-gray-100'
            }`;
        }
    }

    /**
     * Register event handler for WebSocket events
     */
    on(event, handler) {
        if (!this.eventHandlers[event]) {
            this.eventHandlers[event] = [];
        }
        this.eventHandlers[event].push(handler);
    }

    /**
     * Emit event to all registered handlers
     */
    emit(event, data) {
        if (this.eventHandlers[event]) {
            this.eventHandlers[event].forEach(handler => handler(data));
        }
    }

    /**
     * Initialize Global Notification WebSocket
     */
    initNotificationSocket() {
        const socketId = 'notifications';
        if (this.sockets[socketId]) {
            this.sockets[socketId].close();
        }

        const url = `${this.protocol}://${this.host}/ws/notifications/`;
        const socket = new WebSocket(url);

        socket.onopen = (e) => {
            console.log('✓ Notification WebSocket connected');
            this.updateSocketStatus(socketId, 'connected');
        };

        socket.onmessage = (e) => {
            const message = JSON.parse(e.data);
            this.handleNotificationMessage(message);
        };

        socket.onerror = (error) => {
            console.error('✗ Notification WebSocket error:', error);
            this.updateSocketStatus(socketId, 'error');
        };

        socket.onclose = (e) => {
            console.log('✗ Notification WebSocket closed');
            this.updateSocketStatus(socketId, 'closed');
            setTimeout(() => this.initNotificationSocket(), 5000);
        };

        this.sockets[socketId] = socket;
    }

    /**
     * Handle global notification messages
     */
    handleNotificationMessage(message) {
        if (message.type === 'notification') {
            console.log('🔔 New Notification:', message.data);
            
            // 1. Update Badge Count
            const badge = document.getElementById('global-notif-count');
            if (badge) {
                const currentCount = parseInt(badge.textContent) || 0;
                badge.textContent = currentCount + 1;
                badge.classList.remove('hidden');
                badge.style.animation = 'pulse 1s cubic-bezier(0.4, 0, 0.6, 1) 3';
            } else {
                // If badge doesn't exist, we might need to inject it into the bell link
                const bellLink = document.querySelector('a[href$="/notifications/"]');
                if (bellLink) {
                    const newBadge = document.createElement('span');
                    newBadge.id = 'global-notif-count';
                    newBadge.className = 'absolute top-1 right-1 flex h-4 w-4 items-center justify-center bg-red-500 rounded-full text-[9px] font-black text-white border-2 border-white dark:border-gray-900 shadow-sm';
                    newBadge.textContent = '1';
                    bellLink.appendChild(newBadge);
                }
            }

            // 2. Show Premium Toast
            this.showNotificationToast(message.data.title, message.data.message);
            
            // 3. Play subtle sound if possible
            try { new Audio('/static/sounds/notification.mp3').play(); } catch(e){}
        }
    }

    /**
     * Show MNC-standard Notification Toast
     */
    showNotificationToast(title, message) {
        let toastContainer = document.getElementById('global-toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'global-toast-container';
            toastContainer.className = 'fixed top-20 right-4 z-[9999] flex flex-col gap-3 max-w-[320px] w-full pointer-events-none';
            document.body.appendChild(toastContainer);
        }

        const toast = document.createElement('div');
        toast.className = 'glass-panel p-4 rounded-2xl shadow-elevated border-brand/20 translate-x-12 opacity-0 transition-all duration-500 pointer-events-auto cursor-pointer';
        toast.innerHTML = `
            <div class="flex items-start gap-3">
                <div class="w-10 h-10 rounded-full bg-brand/10 flex items-center justify-center flex-shrink-0">
                    <i class="bi bi-bell-fill text-brand"></i>
                </div>
                <div class="flex-1 min-w-0">
                    <p class="text-sm font-black text-gray-900 dark:text-white mb-0.5">${title}</p>
                    <p class="text-xs text-gray-500 dark:text-gray-400 leading-tight line-clamp-2">${message}</p>
                </div>
            </div>
        `;

        toastContainer.appendChild(toast);
        requestAnimationFrame(() => {
            toast.classList.remove('translate-x-12', 'opacity-0');
            toast.classList.add('translate-x-0', 'opacity-100');
        });

        toast.onclick = () => window.location.href = '/notifications/';

        setTimeout(() => {
            toast.classList.add('translate-x-12', 'opacity-0');
            setTimeout(() => toast.remove(), 500);
        }, 6000);
    }
}

// Initialize global WebSocket manager
const wsManager = new WebSocketManager();

// Initialize sockets globally
document.addEventListener('DOMContentLoaded', () => {
    // 1. Mandatory Global Sockets
    wsManager.initNotificationSocket();

    // 2. Contextual Sockets
    if (document.getElementById('stock-qty-1') || document.querySelector('[data-id]')) {
        wsManager.initInventorySocket();
    }

    const orderIdElement = document.querySelector('[data-order-id]');
    if (orderIdElement) {
        wsManager.initOrderSocket(orderIdElement.dataset.orderId);
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    wsManager.closeAll();
});
