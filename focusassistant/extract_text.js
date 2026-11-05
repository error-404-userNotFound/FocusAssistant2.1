// Bounded iterative DFS, ported from FocusAssistant's extension.
// No UI injection/form interaction. A random per-document identity is attached
// to window so a reload/reordered Safari tab cannot reuse an old close decision.
(() => {
    const key = '__focusAssistant2DocumentToken';
    if (!Object.prototype.hasOwnProperty.call(window, key)) {
        const words = new Uint32Array(4);
        crypto.getRandomValues(words);
        Object.defineProperty(window, key, {value:Array.from(words, n=>n.toString(16)).join('-'), writable:false});
    }
    const excluded = new Set(['SCRIPT','STYLE','NOSCRIPT','TEMPLATE','SVG','CANVAS','IFRAME','OBJECT','INPUT','TEXTAREA']);
    const stack = document.body ? [document.body] : [];
    const parts = [];
    let visited = 0, characters = 0;
    while (stack.length && visited < 9000 && characters < 24000) {
        const node = stack.pop();
        visited++;
        if (node.nodeType === 3) {
            const text = (node.nodeValue || '').replace(/\s+/g, ' ').trim().slice(0, 24000 - characters);
            if (text) { parts.push(text); characters += text.length; }
        } else if (node.nodeType === 1) {
            if (excluded.has(node.tagName) || node.hidden || node.getAttribute('aria-hidden') === 'true' || node.isContentEditable) continue;
            const style = window.getComputedStyle(node);
            if (style.display === 'none' || ['hidden','collapse'].includes(style.visibility) || style.opacity === '0') continue;
            const count = Math.min(node.childNodes.length, 9000 - visited - stack.length);
            for (let i = count - 1; i >= 0; i--) stack.push(node.childNodes[i]);
        }
    }
    return JSON.stringify({url:location.href, title:document.title || '', text:parts.join(' ').slice(0,24000), document_id:window[key], page_fullscreen:!!document.fullscreenElement});
})()
