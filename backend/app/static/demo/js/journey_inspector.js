import { DemoMap } from './map.js';

const map = new DemoMap('map').map;
map.options.preferCanvas = true;
const evidenceLayer = L.layerGroup().addTo(map), guidanceLayer = L.layerGroup().addTo(map);
const regionLayer = L.layerGroup().addTo(map);
const tripSelect = document.getElementById('trip'), versionSelect = document.getElementById('guidance');
const status = document.getElementById('status');
let examples = [], current = null, revision = 0;
const number = value => Number.isFinite(value) ? value.toFixed(1) : 'chưa đủ bằng chứng';
async function request(path, options) {
    const response = await fetch('/api/v1/routing/' + path, options);
    if (!response.ok) throw new Error(`Không tải được bằng chứng (HTTP ${response.status}).`);
    return response.json();
}
function metric(label, value, container = document.getElementById('summary')) {
    const row = document.createElement('div'); row.className = 'metric';
    row.textContent = `${label}: ${value}`; container.append(row);
}
function drawGuidance() {
    guidanceLayer.clearLayers();
    const version = current?.guidance_versions[Number(versionSelect.value)];
    if (version) L.polyline(version.coordinates, { color: '#2563eb', weight: 3, dashArray: '8 5' }).addTo(guidanceLayer);
}
async function selectTrip() {
    const ticket = ++revision;
    current = null; evidenceLayer.clearLayers(); guidanceLayer.clearLayers();
    document.getElementById('summary').replaceChildren(); document.getElementById('unknown').replaceChildren();
    versionSelect.replaceChildren(); status.textContent = 'Đang đối chiếu chuyến…';
    try {
        const result = await request('inspect-guided-trip', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(examples[Number(tripSelect.value)]) });
        if (ticket !== revision) return;
        current = result;
        const summary = result.summary, comparison = result.whole_trip_comparison;
        metric('Đường GPS trùng chỉ dẫn ban đầu', `${number(comparison.shared_pct_on_actual)}${comparison.status === 'AVAILABLE' ? '%' : ''}`);
        metric('Chỉ dẫn ban đầu đã được đi qua', `${number(comparison.shared_pct_on_proposed)}${comparison.status === 'AVAILABLE' ? '%' : ''}`);
        if (comparison.status !== 'AVAILABLE') metric('Lý do chưa có phần trăm', {
            COMPARISON_WORK_LIMIT: 'Vượt giới hạn của phép so sánh toàn tuyến; các đoạn đã đối chiếu vẫn được hiển thị.',
            UNAVAILABLE_GPS_CONTINUITY: 'Thiếu GPS liên tục hoặc thiếu đầu/cuối chuyến.',
            NO_OBSERVED_MOVEMENT: 'Không có quãng đường quan sát để tính tỷ lệ.'
        }[comparison.status] || 'Chưa đủ bằng chứng.');
        metric('Đoạn lệch đã xác nhận', `${number(summary.off_route_distance_m / 1000)} km · ${number(summary.off_route_seconds)} giây`);
        metric('Thời gian chưa xác minh', `${number(summary.unknown_seconds)} giây`);
        metric('Số lần bắt đầu lệch', String(summary.departure_events));
        result.guidance_versions.forEach((version, index) => {
            const option = new Option(`Chỉ dẫn ${index + 1} · ${version.effective_at}`, String(index));
            versionSelect.add(option);
        });
        const colors = { ON_ROUTE: '#059669', OFF_ROUTE: '#dc2626', UNKNOWN: '#94a3b8' };
        for (const state of Object.keys(colors)) {
            const paths = result.intervals.filter(interval => interval.state === state && interval.coordinates.length > 1)
                .map(interval => interval.coordinates);
            if (paths.length) L.polyline(paths, { color: colors[state], weight: state === 'OFF_ROUTE' ? 6 : 4,
                ...(state === 'UNKNOWN' ? { dashArray: '4 6' } : {}) }).addTo(evidenceLayer);
        }
        for (const [cell, count] of Object.entries(result.departure_origin_cells)) {
            L.circleMarker(h3.cellToLatLng(cell), { color: '#7c3aed', radius: 7 }).bindPopup(
                `${count} lần bắt đầu lệch trong ô H3 này; tâm ô không phải vị trí rẽ chính xác.`).addTo(evidenceLayer);
        }
        drawGuidance();
        const coordinates = result.intervals.flatMap(interval => interval.coordinates);
        if (coordinates.length) map.fitBounds(L.latLngBounds(coordinates), { padding: [25, 25], maxZoom: 15 });
        const unknown = result.intervals.filter(interval => interval.state === 'UNKNOWN');
        if (unknown.length > 100) metric('Danh sách', `Hiện 100 trên ${unknown.length} khoảng chưa xác minh`, document.getElementById('unknown'));
        unknown.slice(0, 100).forEach(interval => metric(`${interval.from_iso} → ${interval.to_iso}`,
            `${interval.seconds} giây${interval.coordinates.length ? '' : ' · không nối đường'}`, document.getElementById('unknown')));
        status.textContent = `Đã đối chiếu ${result.intervals.length} khoảng GPS. ${unknown.length} khoảng chưa xác minh.`;
    } catch (error) { if (ticket === revision) status.textContent = error.message; }
}
tripSelect.addEventListener('change', selectTrip);
versionSelect.addEventListener('change', drawGuidance);
try {
    const result = await request('guided-examples'); examples = result.examples;
    examples.forEach((example, index) => tripSelect.add(new Option(`Chuyến mẫu ${index + 1} · ${example.started_at}`, String(index))));
    tripSelect.disabled = !examples.length;
    if (examples.length) await selectTrip(); else status.textContent = 'Chưa có chuyến mẫu theo cặp.';
} catch (error) { status.textContent = error.message; }
try {
    const report = await request('coverage-report'), container = document.getElementById('coverage');
    container.replaceChildren();
    metric('Độ phủ đường tham chiếu theo khoảng cách GPS', `${number(report.reference_coverage_pct)}%`, container);
    metric('Chiều dài đường tham chiếu', `${number(report.reference_length_m / 1000)} km`, container);
    metric('Độ phủ đường được phép đi', 'chưa xác minh toàn bộ quyền đi ô tô', container);
    metric('Thời điểm báo cáo', report.as_of, container);
    if (report.scope?.missing_map_area) metric('Phạm vi bản đồ',
        'Bản đồ đang nhập nhỏ hơn vùng đánh giá; chưa thể phủ toàn Hà Nội.', container);
    if (report.available_reference_coverage_pct != null) metric('Phủ tham chiếu trong khung có bản đồ',
        `${number(report.available_reference_coverage_pct)}% · vẫn chưa xác minh mọi quyền đi ô tô`, container);
    const table = document.createElement('table');
    const head = table.insertRow(); ['Vùng địa lý', 'Phủ tham chiếu', 'Còn thiếu (km)'].forEach(text => {
        const cell = document.createElement('th'); cell.textContent = text; head.append(cell);
    });
    report.regions.forEach((region, index) => {
        const row = table.insertRow();
        const button = document.createElement('button'); button.textContent = `Xem vùng ${index + 1}`;
        button.addEventListener('click', () => {
            regionLayer.clearLayers();
            const boundary = h3.cellToBoundary(region.region);
            L.polygon(boundary, { color: '#64748b', fill: false, dashArray: '5 5' }).addTo(regionLayer);
            map.fitBounds(L.latLngBounds(boundary), { padding: [25, 25] });
        });
        row.insertCell().append(button);
        [`${number(region.coverage_pct)}%`, number((region.reference_length_m - region.covered_length_m) / 1000)]
            .forEach(text => { const cell = row.insertCell(); cell.textContent = text; });
    });
    container.append(table); metric('Giới hạn', report.limitations, container);
} catch (error) { document.getElementById('coverage').textContent = error.message; }
