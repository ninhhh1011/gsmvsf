import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';

const output = 'runtime/h3-departures/browser';
mkdirSync(output, { recursive: true });
const url = process.env.H3_REVIEW_URL || 'http://127.0.0.1:8005/demo';
const results = [];
function check(name, passed, evidence) {
    results.push({ name, passed, evidence });
    writeFileSync(`${output}/results.json`, JSON.stringify(results, null, 2));
    if (!passed) throw new Error(`${name}: ${JSON.stringify(evidence)}`);
}
const browser = await chromium.launch({ headless: true });
try {
    for (const [name, viewport] of [['desktop', { width: 1440, height: 900 }], ['mobile', { width: 390, height: 844 }]]) {
        const page = await browser.newPage({ viewport });
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(url, { waitUntil: 'domcontentloaded' });
        await page.waitForFunction(() => !!window.driverMode?._h3Overlay);
        // Fixed replay time matches the documented synthetic verification batch.
        await page.evaluate(() => { driverMode.offlineEvaluationTime = '2026-10-14T03:00:00Z'; });
        if (!await page.locator('#toggle-route-familiarity').isVisible()) await page.locator('#btn-driver-sheet-toggle').click();
        if (!await page.locator('#toggle-route-familiarity').isVisible()) await page.locator('#driver-analysis-tools > summary').click();
        await page.locator('#toggle-route-familiarity').check();
        await page.waitForFunction(() => driverMode._h3Overlay.heatmap?.status === 'AVAILABLE');
        await page.waitForFunction(() => driverMode._h3Overlay.rendered === driverMode._h3Overlay.polygons.length);
        const initial = await page.evaluate(() => ({
            mode: driverMode.h3Mode, routeAbsent: !driverMode.directRouteGeometry,
            polygons: driverMode._h3Overlay.polygons.length, resolution: driverMode._h3Overlay.route.resolution,
            stats: driverMode._h3Overlay.heatmap,
            caption: document.getElementById('route-familiarity-support').textContent
        }));
        const actualCells = new Set(Object.keys(initial.stats.cells));
        const evidenceOnly = await page.evaluate(() => driverMode._h3Overlay.polygons.every(
            p => Object.hasOwn(driverMode._h3Overlay.heatmap.cells, p._cellId)));
        check(`${name}: journey evidence without A/B`, initial.mode === 'DEPARTURES' && initial.routeAbsent &&
            initial.polygons <= actualCells.size && evidenceOnly && initial.resolution === 9,
            { rendered: initial.polygons, supported: actualCells.size, resolution: initial.resolution });
        check(`${name}: paired synthetic evidence is explicit`, initial.stats.source === 'synthetic' && initial.caption.includes('giả lập'), initial.caption);
        check(`${name}: legacy footprints retained without weights`, initial.stats.excluded_unpaired_trip_count > 0 &&
            Object.values(initial.stats.cells).some(c => c.status === 'HISTORY_ONLY' && c.history_trip_count > 0 && c.departure_pct === null),
            { legacyTrips: initial.stats.excluded_unpaired_trip_count, supportedCells: actualCells.size });
        const grayPopup = await page.evaluate(() => {
            const overlay = driverMode._h3Overlay;
            const gray = overlay.polygons.find(p => overlay.heatmap.cells[p._cellId].status === 'HISTORY_ONLY');
            return gray?.getPopup()?.getContent();
        });
        check(`${name}: gray popup does not invent a percentage`, !!grayPopup && !grayPopup.includes('null%') &&
            !grayPopup.includes('0%'), grayPopup);
        const stability = await page.evaluate(() => {
            const overlay = driverMode._h3Overlay, map = driverMode.map.map;
            const before = new Map(overlay.polygons.map(p => [p._cellId, p]));
            let clears = 0;
            const clear = overlay.layer.clearLayers;
            overlay.layer.clearLayers = function (...args) { clears++; return clear.apply(this, args); };
            map.panBy([30, 20], { animate: false });
            map.setZoom(map.getZoom() + 1, { animate: false });
            overlay.layer.clearLayers = clear;
            const retained = overlay.polygons.filter(p => before.has(p._cellId));
            return { clears, retained: retained.length,
                reused: retained.every(p => before.get(p._cellId) === p), resolution: overlay.route.resolution };
        });
        check(`${name}: pan and zoom preserve polygons without clearing`, stability.clears === 0 &&
            stability.retained > 0 && stability.reused && stability.resolution === 9, stability);
        await page.waitForFunction(() => driverMode._h3Overlay.rendered === driverMode._h3Overlay.polygons.length);
        await page.screenshot({ path: `${output}/${name}-journey-footprint.png` });
        if (name === 'mobile') await page.locator('#btn-driver-sheet-toggle').click();
        await page.evaluate(() => driverMode.map.map.setView([21.001, 105.8], 15, { animate: false }));
        await page.waitForFunction(() => driverMode._h3Overlay.heatmap?.status === 'AVAILABLE' && driverMode._h3Overlay.route.resolution >= 9);
        await page.waitForFunction(() => driverMode._h3Overlay.rendered === driverMode._h3Overlay.polygons.length);
        const details = await page.evaluate(() => {
            const overlay = driverMode._h3Overlay;
            const polygon = overlay.polygons.find(p => overlay.cellMetadata.get(p._cellId)?.departure_event_count > 0);
            polygon?.openPopup();
            return { event: overlay.cellMetadata.get(polygon?._cellId), popupOpened: !!polygon?.isPopupOpen(), cells: overlay.polygons.length };
        });
        check(`${name}: actual event popup`, details.popupOpened && details.event?.departure_event_count > 0 && details.event.departure_pct > 0, details.event);
        await page.screenshot({ path: `${output}/${name}-departure-popup.png` });
        if (name === 'mobile') await page.locator('#btn-driver-sheet-toggle').click();
        await page.locator('#h3-analysis-mode').selectOption('COMPARISON');
        await page.waitForFunction(() => driverMode.h3Mode === 'COMPARISON' && !driverMode._h3Overlay.heatmapMode);
        check(`${name}: comparison mode is separate`, await page.evaluate(() => !driverMode._h3Overlay.comparisonMode && !driverMode.directRouteGeometry));
        await page.locator('#h3-analysis-mode').selectOption('DEPARTURES');
        await page.waitForFunction(() => driverMode._h3Overlay.heatmap?.status === 'AVAILABLE' && driverMode._h3Overlay.heatmapMode);
        await page.locator('#toggle-route-familiarity').uncheck();
        check(`${name}: toggle hides grid`, await page.evaluate(() => !driverMode._h3Overlay.enabled && !driverMode._h3Overlay.layer.getLayers().length));
        check(`${name}: no browser errors`, errors.length === 0, errors);
        await page.close();
    }
} finally {
    await browser.close();
}
console.log(JSON.stringify({ passed: results.filter(r => r.passed).length, total: results.length }));
