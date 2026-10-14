import test from 'node:test';
import assert from 'node:assert/strict';
import { DemoMap } from '../../backend/app/static/demo/js/map.js';

test('base map uses the canonical tile host and reports failures separately from H3', () => {
    const original = globalThis.L, events = {}, notices = new Map();
    let url;
    const map = { setView() { return this; }, attributionControl: {
        addAttribution: text => notices.set(text, (notices.get(text) || 0) + 1),
        removeAttribution: text => { const count = notices.get(text) - 1; if (count) notices.set(text, count); else notices.delete(text); } } };
    globalThis.L = { map: () => map, control: { zoom: () => ({ addTo() {} }) },
        layerGroup: () => ({ addTo() { return this; } }), tileLayer: target => {
            url = target;
            return { addTo() { return this; }, on(names, fn) { for (const name of names.split(' ')) events[name] = fn; return this; } };
        } };
    try {
        Object.assign(Object.create(DemoMap.prototype), { layers: {} }).init({});
        assert.equal(url, 'https://tile.openstreetmap.org/{z}/{x}/{y}.png');
        const failed = {}, neighbor = {};
        events.tileerror({ tile: failed }); events.tileerror({ tile: failed });
        events.tileload({ tile: neighbor });
        assert.equal(notices.size, 1);
        events.tileunload({ tile: failed });
        assert.equal(notices.size, 0);
        events.tileerror({ tile: failed }); events.tileload({ tile: failed });
        assert.equal(notices.size, 0);
    } finally { if (original === undefined) delete globalThis.L; else globalThis.L = original; }
});
