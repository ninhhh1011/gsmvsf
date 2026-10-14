import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';

const output = 'runtime/h3-evidence-browser';
mkdirSync(output, { recursive: true });
const checks = [];
function check(name, passed, evidence) {
    checks.push({ name, passed, evidence });
    writeFileSync(`${output}/results.json`, JSON.stringify(checks, null, 2));
    if (!passed) throw new Error(`${name}: ${JSON.stringify(evidence)}`);
}
const browser = await chromium.launch();
try {
    for (const [name, viewport] of [['desktop', { width: 1440, height: 900 }], ['mobile', { width: 390, height: 844 }]]) {
        const page = await browser.newPage({ viewport });
        const errors = [];
        page.on('pageerror', e => errors.push(e.message));
        await page.route('https://tile.openstreetmap.org/**', route => route.abort());
        await page.goto('http://127.0.0.1:8005/demo/static/journeys.html');
        await page.waitForFunction(() => document.getElementById('status').textContent.startsWith('Đã đối chiếu'));
        await page.waitForFunction(() => document.querySelector('#coverage table'));
        check(`${name}: examples and coverage loaded`, await page.locator('#trip option').count() >= 6);
        const examples = await page.locator('#trip option').count();
        for (let index = 0; index < examples; index++) {
            await page.locator('#trip').selectOption(String(index));
            await page.waitForFunction(() => document.getElementById('status').textContent.startsWith('Đã đối chiếu'));
            const summary = await page.locator('#summary').innerText();
            check(`${name}: sample ${index + 1} explains both denominators and unknown time`,
                summary.includes('Đường GPS trùng chỉ dẫn ban đầu') && summary.includes('Chỉ dẫn ban đầu đã được đi qua') &&
                summary.includes('Thời gian chưa xác minh') && summary.includes('Số lần bắt đầu lệch'), summary);
        }
        const rapid = page.locator('#trip');
        await rapid.selectOption('0'); await rapid.selectOption(String(examples - 1));
        await page.waitForFunction(() => document.getElementById('status').textContent.startsWith('Đã đối chiếu'));
        await page.screenshot({ path: `${output}/${name}.png`, fullPage: true });
        check(`${name}: mobile layout has no horizontal page overflow`, await page.evaluate(
            () => document.documentElement.scrollWidth <= window.innerWidth));
        check(`${name}: no page errors`, errors.length === 0, errors);
        await page.close();
    }
} finally { await browser.close(); }
console.log(JSON.stringify({ passed: checks.filter(c => c.passed).length, total: checks.length }));
