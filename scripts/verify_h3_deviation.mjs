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

    // 3. Click btn-sample-deviation to load deviation scenario directly via UI
    console.log('3. Clicking #btn-sample-deviation to load deviation scenario...');
    await page.locator('#btn-sample-deviation').click();
    await page.waitForTimeout(2500);

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
