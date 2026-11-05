// Observation bridge in macOS JXA, not a browser extension. No input/tab control.
ObjC.import('AppKit');
function foreground() {
    const a = $.NSWorkspace.sharedWorkspace.frontmostApplication;
    return {bundle:ObjC.unwrap(a.bundleIdentifier) || '', app_name:ObjC.unwrap(a.localizedName) || 'Unknown application', process_id:Number(a.processIdentifier)};
}

// Separate adapter function permits testing a known disposable window without
// moving the user's foreground window. Production run() only passes windows[0].
function readSelectedPage(app, w, front, extractor, metadataOnly=false) {
    const chrome = front.bundle === 'com.google.Chrome';
    let result = Object.assign({}, front);
    try {
        const t = chrome ? w.activeTab() : w.currentTab();
        result.window_id = String(w.id());
        result.tab_id = chrome ? String(t.id()) : String(t.index());
        result.url = (t.url() || '').slice(0,8192);
        result.title = ((chrome ? t.title() : t.name()) || '').slice(0,500);
        if (metadataOnly) {
            try {
                const js = 'JSON.stringify({token:window.__focusAssistant2DocumentToken || "", fullscreen:!!document.fullscreenElement})';
                const state = JSON.parse(chrome ? t.execute({javascript:js}) : app.doJavaScript(js, {in:t}));
                result.document_id = state.token;
                result.page_fullscreen = state.fullscreen;
            } catch (_) { result.document_id = ''; }
            return result;
        }
        if (!/^https?:\/\//i.test(result.url)) {
            result.error = 'Only HTTP/HTTPS pages are classified.';
            return result;
        }
        try {
            const raw = chrome ? t.execute({javascript:extractor}) : app.doJavaScript(extractor, {in:t});
            const extracted = JSON.parse(raw);
            if (extracted.url !== result.url || extracted.title.slice(0,500) !== result.title)
                throw Error('The page changed while its text was being read.');
            result.text = extracted.text.slice(0,24000);
            result.document_id = extracted.document_id || '';
            result.page_fullscreen = !!extracted.page_fullscreen;
            result.text_source = 'bounded DOM traversal';
        } catch (e) {
            if (chrome) result.error = String(e);
            else {
                // Safari exposes a native page-text property even with JS automation off.
                result.text = (t.text() || '').slice(0,24000);
                result.text_source = 'Safari native text';
            }
        }
        const current = chrome ? w.activeTab() : w.currentTab();
        const identity = chrome ? String(current.id()) : String(current.index());
        if (identity !== result.tab_id || current.url() !== result.url ||
            ((chrome ? current.title() : current.name()) || '').slice(0,500) !== result.title) {
            return Object.assign({}, front, {error:'The selected page changed during observation; retrying.'});
        }
    } catch (e) {
        result.text = '';
        result.error = String(e);
    }
    return result;
}

function run(argv) {
    const p = JSON.parse(argv[0]);
    const front = foreground();
    if (p.action === 'foreground') return JSON.stringify(front);
    if (!['com.apple.Safari','com.google.Chrome'].includes(front.bundle)) return JSON.stringify(front);
    // Safari's /Applications stub can report running() == false while the
    // active system Safari is running. Resolve the actual app by bundle ID.
    const app = Application(front.bundle);
    try {
        if (!app.running() || !app.windows().length) throw Error('No browser window is available.');
        const result = readSelectedPage(app, app.windows[0], front, p.extractor, p.action === 'metadata');
        const after = foreground();
        if (after.bundle !== front.bundle || !app.windows().length ||
            result.window_id && String(app.windows[0].id()) !== result.window_id) {
            return JSON.stringify(Object.assign({}, after, {error:'The active page changed during observation; retrying.'}));
        }
        return JSON.stringify(result);
    } catch (e) {
        return JSON.stringify(Object.assign({}, front, {error:String(e)}));
    }
}
