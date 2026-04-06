/**
 * JOE Cafeteria Global Hardware & Software Scanner Logic
 */

let html5QrcodeScanner = null;
let isProcessingQR = false;
let scannerBuffer = "";
let lastKeyTime = Date.now();

// Configuration (to be set by the page)
const scannerConfig = {
    scanUrl: "/dashboard/scan_qr/",
    serveUrl: "/dashboard/update_item/", // Default, can be overridden
    csrfToken: ""
};

/**
 * Global Keyboard Listener for Hardware Scanners (HID)
 */
document.addEventListener("keydown", (e) => {
    // Only active for staff roles (check set by base.html inclusion)
    const currentTime = Date.now();
    const timeDiff = currentTime - lastKeyTime;
    lastKeyTime = currentTime;

    if (timeDiff > 50) {
        scannerBuffer = "";
    }

    if (e.key === "Enter") {
        if (scannerBuffer.length > 5) {
            console.log("Hardware Scan:", scannerBuffer);
            onScanSuccess(scannerBuffer);
            scannerBuffer = "";
            e.preventDefault();
        }
    } else if (e.key.length === 1) {
        scannerBuffer += e.key;
    }
});

function toggleQRModal() {
    const modal = document.getElementById('qr-modal');
    if (!modal) return;

    if (modal.classList.contains('hidden')) {
        modal.classList.remove('hidden');
        setTimeout(() => {
            modal.classList.remove('opacity-0');
            modal.children[0].classList.remove('scale-95');
            startQRScanner();
        }, 10);
    } else {
        modal.classList.add('opacity-0');
        modal.children[0].classList.add('scale-95');
        setTimeout(() => {
            modal.classList.add('hidden');
            stopQRScanner();
        }, 300);
    }
}

function startQRScanner() {
    if (typeof Html5Qrcode === 'undefined') return;
    if (!html5QrcodeScanner) {
        html5QrcodeScanner = new Html5Qrcode("reader");
    }
    
    const config = { fps: 10, qrbox: { width: 250, height: 250 }, aspectRatio: 1.0 };
    html5QrcodeScanner.start({ facingMode: "environment" }, config, onScanSuccess)
    .catch(err => {
        console.error("Camera access failed", err);
        const feedback = document.getElementById('scan-feedback');
        if (feedback) {
            feedback.classList.remove('hidden', 'bg-green-100', 'text-green-800');
            feedback.classList.add('bg-red-100', 'text-red-800');
            feedback.innerHTML = "Camera permission denied or unavailable.";
        }
    });
}

function stopQRScanner() {
    if (html5QrcodeScanner && html5QrcodeScanner.isScanning) {
        html5QrcodeScanner.stop().catch(console.error);
    }
}

function onScanSuccess(decodedText) {
    if (isProcessingQR) return;
    isProcessingQR = true;

    // Beep sound
    const beep = document.getElementById('scan-beep');
    if (beep) {
        beep.volume = 0.5;
        beep.play().catch(() => {});
    }

    const feedback = document.getElementById('scan-feedback');
    if (feedback) {
        feedback.classList.remove('hidden', 'bg-red-100', 'text-red-800', 'bg-green-100', 'text-green-800');
        feedback.classList.add('bg-blue-100', 'text-blue-800');
        feedback.innerHTML = '<i class="bi bi-arrow-repeat animate-spin"></i> Validating order...';
    }

    fetch(scannerConfig.scanUrl, {
        method: 'POST',
        headers: {
            'X-CSRFToken': scannerConfig.csrfToken || document.querySelector('[name=csrfmiddlewaretoken]')?.value,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ qr_code_id: decodedText })
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'ok') {
            if (feedback) {
                feedback.classList.remove('bg-blue-100', 'text-blue-800');
                feedback.classList.add('bg-green-100', 'text-green-800');
                feedback.innerHTML = `<i class="bi bi-check-circle-fill"></i> Order #${data.order.id} validated!`;
            }
            
            setTimeout(() => {
                const qrModal = document.getElementById('qr-modal');
                if (qrModal && !qrModal.classList.contains('hidden')) toggleQRModal();
                
                // If dashboard WS update function exists
                if (typeof updateDashboardSections === 'function') updateDashboardSections();
                
                openScannedModal(data.order);
                isProcessingQR = false;
                if (feedback) feedback.classList.add('hidden');
            }, 800);
        } else {
            if (feedback) {
                feedback.classList.remove('bg-blue-100', 'text-blue-800');
                feedback.classList.add('bg-red-100', 'text-red-800');
                feedback.innerHTML = `<i class="bi bi-exclamation-triangle-fill"></i> ${data.message}`;
            } else {
                alert(data.message);
            }
            setTimeout(() => { isProcessingQR = false; }, 3000);
        }
    })
    .catch(err => {
        console.error("Scanner error:", err);
        isProcessingQR = false;
    });
}

function openScannedModal(order) {
    const modal = document.getElementById('scanned-order-modal');
    if (!modal) return;

    document.getElementById('scanned-modal-order-id').innerText = `Scanned Order #${order.id}`;
    document.getElementById('scanned-modal-customer').innerText = order.customer;
    
    const container = document.getElementById('scanned-modal-items-container');
    container.innerHTML = '';
    
    order.items.forEach(item => {
        let actionBtn = '';
        let statusBadge = '';
        
        if (item.status === 'Ready') {
            statusBadge = `<span class="bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-widest"><i class="bi bi-check-circle-fill"></i> Ready Now</span>`;
            actionBtn = `<form onsubmit="globalSubmitAction(event, this); setTimeout(()=>closeScannedModal(), 800);" method="POST" action="${scannerConfig.serveUrl}">
                            <input type="hidden" name="csrfmiddlewaretoken" value="${scannerConfig.csrfToken || document.querySelector('[name=csrfmiddlewaretoken]')?.value}">
                            <input type="hidden" name="order_item_id" value="${item.id}">
                            <input type="hidden" name="status" value="Served">
                            <button type="submit" class="bg-brand text-white px-4 py-2 rounded-xl text-xs font-bold shadow-md hover:bg-orange-600 transition-colors whitespace-nowrap">Serve</button>
                        </form>`;
        } else if (item.status === 'Served') {
            statusBadge = `<span class="bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-widest">Served</span>`;
        } else {
            statusBadge = `<span class="bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-widest"><i class="bi bi-hourglass-split"></i> Prep</span>`;
        }
        
        container.innerHTML += `
            <div class="flex justify-between items-center bg-gray-50 dark:bg-gray-900/50 p-4 rounded-2xl border border-gray-100 dark:border-gray-700/50 shadow-sm mb-3">
                <div>
                    ${statusBadge}
                    <div class="font-bold text-gray-900 dark:text-white mt-1 text-base">${item.quantity}x <span class="font-medium">${item.name}</span></div>
                </div>
                <div>${actionBtn}</div>
            </div>
        `;
    });
    
    modal.classList.remove('hidden');
    setTimeout(() => {
        modal.classList.remove('opacity-0');
        modal.children[0].classList.remove('scale-95');
    }, 10);
}

function closeScannedModal() {
    const modal = document.getElementById('scanned-order-modal');
    if (!modal) return;
    modal.classList.add('opacity-0');
    modal.children[0].classList.add('scale-95');
    setTimeout(() => {
        modal.classList.add('hidden');
    }, 300);
}

function globalSubmitAction(event, form) {
    if (typeof submitAction === 'function') {
        return submitAction(event, form);
    }
    // Fallback if submitAction (dashboard specific) isn't present
    event.preventDefault();
    const formData = new FormData(form);
    fetch(form.action, {
        method: 'POST',
        headers: { 'X-CSRFToken': scannerConfig.csrfToken || document.querySelector('[name=csrfmiddlewaretoken]')?.value },
        body: formData
    }).then(() => {
        if (typeof updateDashboardSections === 'function') updateDashboardSections();
    });
}
