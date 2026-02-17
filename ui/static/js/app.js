/**
 * The Red Phone - Client-side JavaScript
 */

// Prevent zooming on touch devices
document.addEventListener('touchstart', (e) => {
    if (e.touches.length > 1) {
        e.preventDefault();
    }
}, { passive: false });

// Prevent double-tap zoom
let lastTap = 0;
document.addEventListener('touchend', (e) => {
    const now = Date.now();
    if (now - lastTap < 300) {
        e.preventDefault();
    }
    lastTap = now;
}, { passive: false });

// Full screen on click (for kiosk mode)
document.addEventListener('click', () => {
    if (document.documentElement.requestFullscreen && !document.fullscreenElement) {
        // document.documentElement.requestFullscreen().catch(() => {});
    }
});

// Keep screen awake (if supported)
if ('wakeLock' in navigator) {
    navigator.wakeLock.request('screen').catch(() => {});
}

// Connection status indicator
const socket = typeof io !== 'undefined' ? io() : null;

if (socket) {
    socket.on('connect', () => {
        console.log('Connected to server');
    });
    
    socket.on('disconnect', () => {
        console.log('Disconnected from server');
    });
}
