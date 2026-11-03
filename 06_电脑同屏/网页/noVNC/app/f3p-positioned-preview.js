// One live image over the existing noVNC canvas. No extra visible controls.
(() => {
    if (window.f3pPositionedPreview) return;
    const video = document.createElement('img');
    video.alt = '';
    Object.assign(video.style, {position: 'fixed', visibility: 'hidden', pointerEvents: 'none', zIndex: '3', objectFit: 'fill', margin: '0', padding: '0', border: '0'});
    const bridge = document.createElement('iframe');
    bridge.src = 'http://127.0.0.1:5903/bridge';
    bridge.title = 'preview position';
    bridge.tabIndex = -1;
    Object.assign(bridge.style, {position: 'fixed', width: '1px', height: '1px', opacity: '0', pointerEvents: 'none', border: '0'});
    document.body.append(bridge, video);
    const viewer = 'native-' + crypto.randomUUID();
    let geometry = null, updated = 0, streaming = false, ready = false, retryAt = 0, bridgeAttempt = performance.now();
    const diagnostics = window.f3pPositionedPreview = {revision: 'native-image-v2-reconnect', viewer, visible: false, sourceFps: 0};
    function stop() {
        video.style.visibility = 'hidden';
        diagnostics.visible = false;
        if (streaming) video.removeAttribute('src');
        streaming = false;
    }
    function place() {
        const canvas = document.querySelector('#noVNC_container canvas');
        const g = geometry;
        if (document.hidden || !canvas || !g?.visible || performance.now() - updated > 1500) { stop(); return; }
        const v = [g.x, g.y, g.width, g.height];
        if (!v.every(Number.isFinite) || g.x < 0 || g.y < 0 || g.width <= 0 || g.height <= 0 || g.x + g.width > canvas.width || g.y + g.height > canvas.height) { stop(); return; }
        const box = canvas.getBoundingClientRect();
        if (!box.width || !box.height) { stop(); return; }
        const sx = box.width / canvas.width, sy = box.height / canvas.height;
        Object.assign(video.style, {left: (box.left + g.x * sx) + 'px', top: (box.top + g.y * sy) + 'px', width: (g.width * sx) + 'px', height: (g.height * sy) + 'px'});
        if (!streaming && performance.now() >= retryAt) {
            video.src = 'http://127.0.0.1:5903/stream.mjpg?view=embedded&viewer=' + encodeURIComponent(viewer) + '&t=' + Date.now();
            streaming = true;
        }
        // An endless MJPEG response need never reach the image load event.
        video.style.visibility = streaming ? 'visible' : 'hidden';
        diagnostics.visible = streaming;
    }
    video.onerror = () => { stop(); retryAt = performance.now() + 700; };
    bridge.onload = () => { ready = true; };
    window.addEventListener('message', event => {
        if (event.origin !== 'http://127.0.0.1:5903' || event.source !== bridge.contentWindow || event.data?.type !== 'f3p-preview-position') return;
        geometry = event.data.window; updated = performance.now();
        diagnostics.sourceFps = event.data.preview_fps || 0;
        diagnostics.geometry = geometry;
        place();
    });
    document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); else poll(); });
    window.addEventListener('resize', place);
    window.addEventListener('pagehide', stop);
    function poll() {
        if (!document.hidden && performance.now() - Math.max(updated, bridgeAttempt) > 5000) {
            // A failed iframe navigation does not retry when its SSH tunnel returns.
            stop();geometry = null;ready = false;bridgeAttempt = performance.now();
            bridge.src = 'http://127.0.0.1:5903/bridge?retry=' + Date.now();
        }
        if (ready && !document.hidden) bridge.contentWindow.postMessage({type: 'f3p-preview-poll'}, 'http://127.0.0.1:5903');
        place();
    }
    setInterval(poll, 250);
})();
