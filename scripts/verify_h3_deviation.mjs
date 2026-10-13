import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';

const outputDir = 'C:/Users/nguye/.gemini/antigravity-cli/brain/e99f19ed-4d1d-4ee1-9232-5b331673d677';
mkdirSync(outputDir, { recursive: true });

async function main() {
  console.log('Launching browser for H3 deviation verification...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.setDefaultTimeout(60000);

  try {
    // 1. Load app without selecting Point A or B
    console.log('1. Loading http://127.0.0.1:3000...');
    await page.goto('http://127.0.0.1:3000', { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => !!window.driverMode?.currentVehicle);
    await page.waitForTimeout(1000);

    // Verify toggle is NOT disabled
    const toggleDisabled = await page.evaluate(() => document.getElementById('toggle-route-familiarity').disabled);
    console.log('H3 toggle disabled before A/B:', toggleDisabled);
    if (toggleDisabled) throw new Error('H3 toggle should not be disabled before A/B');

    // 2. Click H3 toggle immediately without picking Point A or B
    console.log('2. Clicking H3 toggle without picking A or B...');
    await page.locator('#toggle-route-familiarity').setChecked(true, { force: true });
    await page.waitForFunction(() => driverMode._h3Overlay?.enabled && driverMode._h3Overlay?.polygons?.length > 0);
    await page.waitForTimeout(1500);

    const cellCount = await page.evaluate(() => driverMode._h3Overlay?.polygons?.length || 0);
    console.log('Rendered Hanoi H3 cells count:', cellCount);

    await page.screenshot({ path: `${outputDir}/01_hanoi_wide_h3_grid.png` });
    console.log('Captured 01_hanoi_wide_h3_grid.png');

    // 3. Simulate a Route with Driver Deviation
    console.log('3. Simulating proposed route and deviated driver trajectory...');
    // Proposed Route: Thanh Xuan to Cau Giay (straight northward)
    const proposed = [
      [20.9849, 105.7935],
      [20.9950, 105.7900],
      [21.0050, 105.7870],
      [21.0180, 105.7840],
      [21.0315, 105.7830]
    ];
    // Actual driver trajectory: starts together, then deviates far eastward (+1.2km), then rejoins
    const actual = [
      [20.9849, 105.7935],
      [20.9950, 105.7900],
      [21.0050, 105.8050], // Deviated eastward (~1.5km east)
      [21.0180, 105.8080], // Deviated
      [21.0315, 105.7830]
    ];

    await page.evaluate(({ proposed, actual }) => {
      const overlay = driverMode._h3Overlay;
      const proposedCells = overlay.computeH3CellsFromGeometry(proposed, 9);
      const actualCells = overlay.computeH3CellsFromGeometry(actual, 9);
      const sharedCells = proposedCells.filter(c => actualCells.includes(c));
      const allCells = [...new Set([...proposedCells, ...actualCells])];
      
      overlay.proposedCoords = proposed;
      overlay.renderFromCells(allCells, sharedCells, true);

      const allPoints = [...proposed, ...actual];
      const bounds = L.latLngBounds(allPoints);
      driverMode.map.map.fitBounds(bounds, { paddingTopLeft: [450, 60], paddingBottomRight: [60, 60], maxZoom: 14 });
    }, { proposed, actual });

    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${outputDir}/02_h3_red_deviation_heatmap.png` });
    console.log('Captured 02_h3_red_deviation_heatmap.png');

    // 4. Click on a deviated red cell to inspect popup
    console.log('4. Clicking on a deviated polygon to open popup...');
    const clicked = await page.evaluate(() => {
      const overlay = driverMode._h3Overlay;
      for (const [cell, meta] of overlay.cellMetadata.entries()) {
        if (meta.tier === 'DEVIATION_SEVERE') {
          const poly = overlay.polygons.find(p => p._cellId === cell);
          if (poly) {
            poly.openPopup();
            return { cell, meta, found: true };
          }
        }
      }
      return { found: false };
    });
    console.log('Deviated cell popup info:', clicked);

    await page.waitForTimeout(1000);
    await page.screenshot({ path: `${outputDir}/03_deviation_cell_popup.png` });
    console.log('Captured 03_deviation_cell_popup.png');

    console.log('All verification checks and screenshots completed successfully!');
  } catch (err) {
    console.error('Verification failed:', err);
    await page.screenshot({ path: `${outputDir}/error_deviation.png` });
    throw err;
  } finally {
    await browser.close();
  }
}

main();
