// Control support: topology metadata, guarded DOM-full-screen exit and browser
// activation for approved recovery. Never reads background page bodies.
function run(argv) {
    const p = JSON.parse(argv[0]);
    if (!['com.apple.Safari','com.google.Chrome'].includes(p.bundle)) throw Error('Unsupported browser');
    const app = Application(p.bundle), chrome = p.bundle === 'com.google.Chrome';
    if (p.action === 'exit_dom_fullscreen') {
        ObjC.import('AppKit');
        const front = $.NSWorkspace.sharedWorkspace.frontmostApplication;
        if (ObjC.unwrap(front.bundleIdentifier) !== p.bundle) throw Error('Browser lost focus');
        const w=app.windows[0], t=chrome ? w.activeTab() : w.currentTab();
        if (String(w.id()) !== p.window_id || String(chrome ? t.id() : t.index()) !== p.tab_id || t.url() !== p.url)
            throw Error('Active tab changed before full-screen exit');
        const js='(() => {if(window.__focusAssistant2DocumentToken !== '+JSON.stringify(p.document_id)+') return false; '
            +'if(document.fullscreenElement) {document.exitFullscreen(); return true;} return false;})()';
        return JSON.stringify({requested:chrome ? t.execute({javascript:js}) : app.doJavaScript(js,{in:t})});
    }
    if (p.action === 'activate') {
        if (!app.running()) throw Error('The original browser is no longer running');
        // Activate the existing process without a reopen event that could create
        // a new Start Page window and disturb the verified recovery state.
        ObjC.import('AppKit');
        const running = $.NSRunningApplication.runningApplicationsWithBundleIdentifier(p.bundle);
        if (!Number(running.count)) throw Error('Browser process is unavailable');
        running.objectAtIndex(0).activateWithOptions($.NSApplicationActivateIgnoringOtherApps);
        const target = app.windows().filter(w=>String(w.id()) === p.window_id);
        if (target.length) target[0].index = 1;
        return JSON.stringify({activated:true});
    }
    if (!app.running()) return JSON.stringify([]);
    return JSON.stringify(app.windows().map(w=>({id:String(w.id()), tabs:(w.tabs() || []).map(t=>({
        key:chrome ? String(t.id()) : String(t.index()), url:t.url() || '',
        title:(chrome ? t.title() : t.name()) || ''
    }))})).filter(w=>w.tabs.length).sort((a,b)=>a.id.localeCompare(b.id)));
}
