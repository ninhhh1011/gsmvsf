/**
 * UI Component Renderers for VinFast EV Recommendation Demo.
 * 
 * Strict rule: All energy warnings and recommendation decisions reflect backend truth.
 * No recalculation of scores or energy thresholds.
 */

export function classifyEnergyWarning(energyContext) {
    if (!energyContext) {
        return { level: 'SAFE', title: 'Energy Status: SAFE', message: 'Battery telemetry nominal.', reasonCode: 'NOMINAL' };
    }

    const { need_service, reason_code, estimated_remaining_range_km, remaining_trip_distance_km, energy_margin_km } = energyContext;

    if (!need_service || reason_code === 'SUFFICIENT_SOC_RANGE') {
        return {
            level: 'SAFE',
            title: 'Energy Status: SAFE',
            message: 'Estimated battery range is sufficient for the current trip and reserve buffer.',
            reasonCode: reason_code || 'SUFFICIENT_SOC_RANGE'
        };
    }

    // Critical: Vehicle cannot reach destination
    if (
        reason_code === 'DESTINATION_NOT_REACHABLE' ||
        (estimated_remaining_range_km != null && remaining_trip_distance_km != null && estimated_remaining_range_km < remaining_trip_distance_km)
    ) {
        return {
            level: 'CRITICAL',
            title: 'ENERGY CRITICAL',
            message: 'Estimated range may not be sufficient to complete the current trip. Energy service recommendation available.',
            reasonCode: reason_code || 'DESTINATION_NOT_REACHABLE'
        };
    }

    // Advisory: Destination reachable, but insufficient post-destination reserve
    return {
        level: 'ADVISORY',
        title: 'Energy Reserve Low',
        message: 'You can complete the current trip. Energy service is recommended after drop-off.',
        reasonCode: reason_code || 'INSUFFICIENT_POST_DESTINATION_RESERVE'
    };
}

export function renderEnergyWarningBanner(energyContext) {
    const warning = classifyEnergyWarning(energyContext);
    const badgeClass = warning.level.toLowerCase();

    let iconSvg = '';
    if (warning.level === 'SAFE') {
        iconSvg = `
            <svg class="warning-icon" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
            </svg>
        `;
    } else if (warning.level === 'ADVISORY') {
        iconSvg = `
            <svg class="warning-icon" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
            </svg>
        `;
    } else {
        iconSvg = `
            <svg class="warning-icon" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
            </svg>
        `;
    }

    return `
        <div class="energy-warning-banner banner-${badgeClass}" role="alert">
            <div class="banner-icon">${iconSvg}</div>
            <div class="banner-content">
                <div class="banner-title">${warning.title} <span class="badge-code">${warning.reasonCode}</span></div>
                <div class="banner-desc">${warning.message}</div>
            </div>
        </div>
    `;
}

export function renderRecommendationCard(recResult, onSelectStation = null) {
    if (!recResult || !recResult.has_recommendation) {
        return `
            <div class="recommendation-card empty-card">
                <div class="card-header">
                    <h4>No Service Needed / No Eligible Stations</h4>
                </div>
                <div class="card-body">
                    <p class="muted-text">
                        ${recResult?.reason || 'Current battery state does not require immediate diversion, or no stations match criteria.'}
                    </p>
                </div>
            </div>
        `;
    }

    const topCandidate = recResult.ranked_candidates[0];
    const stId = recResult.recommended_station_id || topCandidate?.station_id;
    const sType = recResult.recommended_service_type || topCandidate?.service_type;
    const isSwap = sType === 'BATTERY_SWAP';

    const etaStationMin = (topCandidate.eta_to_station_s / 60).toFixed(1);
    const etaStartMin = (topCandidate.eta_to_service_start_s / 60).toFixed(1);
    const etaCompleteMin = (topCandidate.eta_to_service_complete_s / 60).toFixed(1);
    const detourMin = topCandidate.features.detour_duration_s != null ? (topCandidate.features.detour_duration_s / 60).toFixed(1) : '0.0';
    const detourDistKm = topCandidate.features.detour_distance_m != null ? (topCandidate.features.detour_distance_m / 1000).toFixed(1) : '0.0';
    const queueWaitMin = (topCandidate.features.effective_queue_wait_s / 60).toFixed(1);
    const serviceMin = (topCandidate.features.service_duration_s / 60).toFixed(1);

    const isDegraded = recResult.degraded;
    const degradedBadges = (recResult.degraded_reasons || []).map(r => `<span class="badge badge-warning">${r}</span>`).join(' ');

    const stationFresh = topCandidate.features.station_state?.freshness || 'FRESH';
    const queueFresh = topCandidate.features.queue_state?.freshness || 'FRESH';

    return `
        <div class="recommendation-card ${isSwap ? 'card-swap' : 'card-charging'}">
            <div class="card-header">
                <div class="rec-title-wrap">
                    <span class="rec-badge-label">RECOMMENDED STOP</span>
                    <h3 class="station-id">${stId}</h3>
                </div>
                <span class="service-type-pill ${isSwap ? 'pill-swap' : 'pill-charging'}">
                    ${isSwap ? '⚡ BATTERY SWAP' : '🔌 EV CHARGING'}
                </span>
            </div>

            <div class="card-grid">
                <div class="metric-item">
                    <span class="metric-label">Travel to Station</span>
                    <span class="metric-val highlight">${etaStationMin} <small>min</small></span>
                </div>
                <div class="metric-item">
                    <span class="metric-label">Queue Wait</span>
                    <span class="metric-val">${queueWaitMin} <small>min</small></span>
                </div>
                <div class="metric-item">
                    <span class="metric-label">Service Time</span>
                    <span class="metric-val">${serviceMin} <small>min</small></span>
                </div>
                <div class="metric-item">
                    <span class="metric-label">Total Completion</span>
                    <span class="metric-val highlight-green">${etaCompleteMin} <small>min</small></span>
                </div>
            </div>

            <div class="detour-bar">
                <span>Detour: <strong>+${detourDistKm} km</strong> (+${detourMin} min)</span>
                <span>Available: <strong>${topCandidate.features.available_capacity} slots</strong></span>
            </div>

            ${isDegraded ? `<div class="degraded-notice">⚠️ Degraded Context: ${degradedBadges}</div>` : ''}

            <div class="card-explanation">
                <div class="exp-title">Why this recommendation?</div>
                <div class="exp-body">
                    Selected to minimize total time: travel to station (${etaStationMin}m) + wait in queue (${queueWaitMin}m) + service (${serviceMin}m) = <strong>${etaCompleteMin} min to complete</strong>.
                </div>
            </div>
        </div>
    `;
}

export function renderPipelineLatency(timingsMs) {
    if (!timingsMs) return '';

    const loc = timingsMs.location_resolution || 0;
    const dem = timingsMs.demand || 0;
    const cand = timingsMs.candidate_search || 0;
    const rank = timingsMs.ranking || 0;
    const total = timingsMs.total || (loc + dem + cand + rank);

    const pct = (val) => Math.max(2, Math.min(100, (val / total) * 100)).toFixed(1);

    return `
        <div class="pipeline-card">
            <div class="pipeline-header">
                <h4>Recommendation Breakdown</h4>
                <span class="total-latency">${total.toFixed(1)} ms</span>
            </div>
            
            <div class="pipeline-progress-bar">
                <div class="bar-seg seg-w1" style="width: ${pct(loc)}%;" title="Location: ${loc.toFixed(2)} ms"></div>
                <div class="bar-seg seg-w2" style="width: ${pct(dem)}%;" title="Demand Detection: ${dem.toFixed(2)} ms"></div>
                <div class="bar-seg seg-w3" style="width: ${pct(cand)}%;" title="Candidate Search: ${cand.toFixed(1)} ms"></div>
                <div class="bar-seg seg-w4" style="width: ${pct(rank)}%;" title="Ranking: ${rank.toFixed(1)} ms"></div>
            </div>

            <div class="pipeline-legend">
                <div class="legend-item"><span class="dot dot-w1"></span> Location: <b>${loc.toFixed(2)} ms</b></div>
                <div class="legend-item"><span class="dot dot-w2"></span> Demand: <b>${dem.toFixed(2)} ms</b></div>
                <div class="legend-item"><span class="dot dot-w3"></span> Candidate Search: <b>${cand.toFixed(1)} ms</b></div>
                <div class="legend-item"><span class="dot dot-w4"></span> Ranking: <b>${rank.toFixed(1)} ms</b></div>
            </div>
        </div>
    `;
}

export function renderCandidateTable(candidates, rankedCandidates = []) {
    if (!candidates || candidates.length === 0) {
        return '<p class="muted-text">No candidate stations evaluated.</p>';
    }

    const rankMap = new Map();
    rankedCandidates.forEach(rc => {
        rankMap.set(`${rc.station_id}_${rc.service_type}`, rc);
    });

    const eligible = candidates.filter(c => c.eligible);
    const ineligible = candidates.filter(c => !c.eligible);

    const renderRow = (c, isEligible) => {
        const key = `${c.station_id}_${c.service_type}`;
        const ranked = rankMap.get(key);
        const rankNum = ranked ? ranked.rank : (isEligible ? '-' : 'N/A');
        const isTop = rankNum === 1;

        const travelMin = c.route_metrics?.duration_to_station_s != null
            ? (c.route_metrics.duration_to_station_s / 60).toFixed(1)
            : (c.network_distance_m != null ? `${(c.network_distance_m / 1000).toFixed(1)} km` : '-');

        const queueMin = c.operational?.estimated_wait_min != null ? c.operational.estimated_wait_min.toFixed(1) : '0.0';
        const detourMin = c.route_metrics?.detour_duration_s != null ? (c.route_metrics.detour_duration_s / 60).toFixed(1) : '-';
        const costMin = ranked ? (ranked.final_cost_s / 60).toFixed(1) : '-';

        return `
            <tr class="${isTop ? 'row-top-rec' : ''} ${!isEligible ? 'row-ineligible' : ''}">
                <td><span class="rank-badge ${isTop ? 'rank-1' : ''}">${rankNum}</span></td>
                <td><strong>${c.station_id}</strong></td>
                <td><span class="badge ${c.service_type === 'BATTERY_SWAP' ? 'badge-purple' : 'badge-teal'}">${c.service_type === 'BATTERY_SWAP' ? 'SWAP' : 'CHARGE'}</span></td>
                <td>${isEligible ? `<span class="badge badge-success">ELIGIBLE</span>` : `<span class="badge badge-danger">${c.reason || 'INELIGIBLE'}</span>`}</td>
                <td>${travelMin} m</td>
                <td>${queueMin} m</td>
                <td>${detourMin} m</td>
                <td>${c.operational?.available_capacity ?? '-'}</td>
                <td><strong>${costMin} m</strong></td>
            </tr>
        `;
    };

    return `
        <div class="candidate-tables-wrapper">
            <div class="table-section">
                <div class="section-title">Eligible Candidates (${eligible.length})</div>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Rank</th>
                            <th>Station</th>
                            <th>Service</th>
                            <th>Status</th>
                            <th>Travel</th>
                            <th>Queue</th>
                            <th>Detour</th>
                            <th>Cap.</th>
                            <th>Total Cost</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${eligible.map(c => renderRow(c, true)).join('')}
                    </tbody>
                </table>
            </div>

            <div class="table-section mt-4">
                <div class="section-title">Ineligible Candidates (${ineligible.length})</div>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>-</th>
                            <th>Station</th>
                            <th>Service</th>
                            <th>Ineligibility Reason</th>
                            <th>Distance</th>
                            <th>Queue</th>
                            <th>-</th>
                            <th>Cap.</th>
                            <th>-</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${ineligible.map(c => renderRow(c, false)).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

export function renderConflictAlert(conflictDetail, onRefresh) {
    return `
        <div class="conflict-alert-card" role="alert">
            <div class="conflict-header">
                <span class="conflict-badge">409 CANDIDATE_STATE_CHANGED</span>
                <h4>Station Availability Changed</h4>
            </div>
            <p>
                One or more candidate stations changed operational eligibility during recommendation processing.
                The ranking model strictly rejected the stale candidate snapshot.
            </p>
            <div class="conflict-actions">
                <button id="btn-refresh-conflict" class="btn btn-primary btn-sm">Refresh Recommendation</button>
            </div>
        </div>
    `;
}
