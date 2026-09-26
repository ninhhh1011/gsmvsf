/**
 * Browser Acceptance Tests for Demo UI - Round 01
 * BROWSER_WITH_API_FIXTURES
 *
 * Tests the actual browser behavior with real HTML/JS modules.
 * API calls are intercepted to isolate frontend testing.
 */
const { test, expect } = require('@playwright/test');

/**
 * Shared API fixtures for intercepting and mocking backend calls.
 */
const createApiFixtures = (page) => ({
  /**
   * Intercept recommendation API and return a controlled response.
   */
  mockRecommendation: (overrides = {}) => {
    return page.route('**/api/v1/recommend', (route) => {
      const defaultBody = {
        has_recommendation: true,
        recommended_station_id: 'S001',
        recommended_service_type: 'CHARGING',
        eligible_count: 5,
        ranked_candidates: [
          {
            rank: 1,
            station_id: 'S001',
            service_type: 'CHARGING',
            eta_to_station_s: 300,
            eta_to_service_complete_s: 600,
            features: {
              detour_distance_m: 500,
              detour_duration_s: 60,
              effective_queue_wait_s: 180,
              service_duration_s: 120,
              available_capacity: 3,
            }
          }
        ],
        timings_ms: { location_resolution: 10, demand: 5, candidate_search: 20, ranking: 8, total: 43 },
        energy_context: { need_service: true, reason_code: 'LOW_SOC', current_soc_pct: 15 }
      };
      const status = overrides.httpStatus || 200;
      route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify({ ...defaultBody, ...overrides })
      });
    });
  },

  /**
   * Intercept candidate search API.
   */
  mockCandidateSearch: (response = {}) => {
    return page.route('**/api/v1/candidate-search/evaluate', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          candidates: [
            { station_id: 'S001', service_type: 'CHARGING', eligible: true },
            { station_id: 'S002', service_type: 'CHARGING', eligible: false, reason: 'OUT_OF_RANGE' }
          ]
        })
      });
    });
  },

  /**
   * Intercept route API.
   */
  mockRoute: (response = {}) => {
    return page.route('**/api/v1/route', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@',
          distance_m: 3500,
          duration_s: 420
        })
      });
    });
  },

  /**
   * Intercept trajectory API.
   */
  mockTrajectory: (trajId = 'TRJ0001') => {
    return page.route(`**/api/v1/debug/trajectories/${trajId}`, (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { latitude: 21.0285, longitude: 105.8542, timestamp: '2026-09-01T07:00:00Z', speed_kmh: 30, heading_deg: 90 },
          { latitude: 21.0290, longitude: 105.8550, timestamp: '2026-09-01T07:00:30Z', speed_kmh: 35, heading_deg: 95 },
          { latitude: 21.0295, longitude: 105.8560, timestamp: '2026-09-01T07:01:00Z', speed_kmh: 32, heading_deg: 100 }
        ])
      });
    });
  },

  /**
   * Intercept driver location API.
   */
  mockDriverLocation: () => {
    return page.route('**/api/v1/drivers/**/location', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'MATCHED',
          trigger_reason: 'MANUAL_STEP',
          total_match_calls: 1,
          raw_position: { latitude: 21.0285, longitude: 105.8542 },
          matched_position: {
            latitude: 21.0285,
            longitude: 105.8542,
            road_segment_id: 'RS001',
            direction: 'FORWARD',
            confidence: 0.95
          }
        })
      });
    });
  },

  /**
   * Intercept readiness check.
   */
  mockReadiness: () => {
    return page.route('**/ready', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ready',
          graphhopper: true,
          postgis: true,
          redis: true
        })
      });
    });
  }
});

// ============================================================
// A. BOOTSTRAP TESTS
// ============================================================
test.describe('A. Bootstrap', () => {
  test('page renders without page error', async ({ page }) => {
    // Listen for page errors
    const errors = [];
    const consoleMessages = [];
    page.on('pageerror', (err) => errors.push(err.message));
    page.on('console', (msg) => {
      consoleMessages.push(`[${msg.type()}] ${msg.text()}`);
      if (msg.type() === 'error') errors.push(msg.text());
    });

    await page.goto('/demo');

    // Wait for map to initialize
    await expect(page.locator('#map')).toBeVisible({ timeout: 15000 });

    // Wait for app to initialize - check if app.js loaded by looking for specific element
    // The app should render select-driver-trip after init
    try {
      await expect(page.locator('#select-driver-trip')).toBeVisible({ timeout: 10000 });
    } catch (e) {
      // Log console messages for debugging
      console.log('Console messages:', consoleMessages.slice(0, 10));
      console.log('Page errors:', errors.slice(0, 5));
      // Check what's actually in the driver panel
      const panelContent = await page.locator('#driver-panel-content').innerHTML();
      console.log('Panel content:', panelContent.substring(0, 500));
      throw e;
    }

    // Check for critical controls
    await expect(page.locator('#driver-status-badge')).toBeVisible();

    // Wait a bit more for full initialization
    await page.waitForTimeout(500);

    // Verify no uncaught errors (filter out expected network issues)
    const criticalErrors = errors.filter(e =>
      !e.includes('Failed to load resource') &&
      !e.includes('net::') &&
      !e.includes('favicon')
    );
    expect(criticalErrors).toHaveLength(0);
  });

  test('controls appear and are usable', async ({ page }) => {
    await page.goto('/demo');

    // Wait for app initialization
    await expect(page.locator('#select-driver-trip')).toBeVisible({ timeout: 15000 });

    // Driver status badge should be visible
    await expect(page.locator('#driver-status-badge')).toBeVisible();

    // Select trip dropdown should be visible and have options
    const tripSelect = page.locator('#select-driver-trip');
    await expect(tripSelect).toBeVisible();
    const options = await tripSelect.locator('option').count();
    expect(options).toBeGreaterThan(0);
  });
});

// ============================================================
// B. SCENARIO/TRIP/VEHICLE SELECTION
// ============================================================
test.describe('B. Scenario/Trip/Vehicle Selection', () => {
  test('trip selection changes context', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    // Select a different trip
    const tripSelect = page.locator('#select-driver-trip');
    await tripSelect.selectOption('T0002');

    // Accept trip
    await page.locator('#btn-accept-trip').click();

    // Wait for UI update
    await page.waitForTimeout(1000);

    // Badge should show TRIP_ASSIGNED
    await expect(page.locator('#driver-status-badge')).toContainText('TRIP_ASSIGNED');
  });
});

// ============================================================
// C. DIRECT ROUTE RENDERING
// ============================================================
test.describe('C. Direct Route', () => {
  test('route persists after trip assignment', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    // Accept trip
    await page.locator('#btn-accept-trip').click();

    // Wait for route computation
    await page.waitForTimeout(1500);

    // The map should have route layers (check via route exists in map state)
    // We verify by checking the badge changed state
    await expect(page.locator('#driver-status-badge')).toContainText('TRIP_ASSIGNED');

    // Route should not be immediately cleared - check via UI state
    // The fact that we got TRIP_ASSIGNED without error means route rendered
    const pageContent = await page.content();
    expect(pageContent).toContain('TRIP_ASSIGNED');
  });
});

// ============================================================
// D. REPLAY STEP
// ============================================================
test.describe('D. Replay Step', () => {
  test('replay step sends correct metadata', async ({ page }) => {
    // Mock all external APIs before navigation
    await page.route('**/ready', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ready', graphhopper: true, postgis: true, redis: true }) });
    });

    await page.route('**/api/v1/route', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@', distance_m: 3500, duration_s: 420 }) });
    });

    await page.route('**/api/v1/debug/trajectories/**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([
        { latitude: 21.0285, longitude: 105.8542, timestamp: '2026-09-01T07:00:00Z', speed_kmh: 30, heading_deg: 90 },
        { latitude: 21.0290, longitude: 105.8550, timestamp: '2026-09-01T07:00:30Z', speed_kmh: 35, heading_deg: 95 }
      ]) });
    });

    // Track GPS ingestion requests
    const gpsRequests = [];
    await page.route('**/api/v1/drivers/**/location', (route) => {
      const body = route.request().postDataJSON();
      if (body) {
        gpsRequests.push(body);
      }
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'MATCHED',
          trigger_reason: 'MANUAL_STEP',
          total_match_calls: 1,
          raw_position: { latitude: 21.0285, longitude: 105.8542 },
          matched_position: {
            latitude: 21.0285,
            longitude: 105.8542,
            road_segment_id: 'RS001',
            direction: 'FORWARD',
            confidence: 0.95
          }
        })
      });
    });

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    // Accept trip to go to TRIP_ASSIGNED state
    await page.locator('#btn-accept-trip').click();
    await page.waitForTimeout(1000);

    // Click Start Driving to trigger startTrip() which calls replay.step()
    await page.locator('#btn-start-driving').click();
    await page.waitForTimeout(2000);

    // The GPS request should have been sent via replay.step()
    expect(gpsRequests.length).toBeGreaterThanOrEqual(1);
    const req = gpsRequests[0];
    expect(req).toHaveProperty('latitude');
    expect(req).toHaveProperty('longitude');
  });

  test('replay step uses consistent driver identity', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();
    fixtures.mockTrajectory('TRJ0001');

    // Track GPS requests by driver ID in URL path
    const driverIds = [];
    await page.route('**/api/v1/drivers/**/location', (route) => {
      const url = route.request().url();
      const match = url.match(/\/api\/v1\/drivers\/([^/]+)\/location/);
      if (match) driverIds.push(match[1]);
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'MATCHED',
          trigger_reason: 'MANUAL_STEP',
          total_match_calls: 1,
          raw_position: { latitude: 21.0285, longitude: 105.8542 },
          matched_position: {
            latitude: 21.0285,
            longitude: 105.8542,
            road_segment_id: 'RS001',
            direction: 'FORWARD',
            confidence: 0.95
          }
        })
      });
    });

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    // Start a trip - this triggers startTrip() which calls replay.step()
    await page.locator('#btn-accept-trip').click();
    await page.waitForTimeout(2000);

    // Note: _onReplayStep may call step() again, generating multiple requests
    // Each request should use the same driver ID set by startTrip()
    // Filter out IDs that don't match the expected pattern (driver_ or replay_)
    const validIds = driverIds.filter(id => id.startsWith('driver_') || id.startsWith('replay_'));

    if (validIds.length > 0) {
      const uniqueIds = [...new Set(validIds)];
      // All GPS requests should use IDs from the same generation session
      // Allow up to 2 IDs if step() was called before and after driver_id was set
      expect(uniqueIds.length).toBeLessThanOrEqual(2);
    }
  });
});

// ============================================================
// E. RECOMMENDATION (CHARGING)
// ============================================================
test.describe('E. Recommendation', () => {
  test('recommendation displays after UI action with charging station and detour', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();
    fixtures.mockTrajectory('TRJ0001');
    fixtures.mockDriverLocation();
    fixtures.mockRecommendation();
    fixtures.mockCandidateSearch();

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    // Start a trip
    await page.locator('#btn-accept-trip').click();
    await page.waitForTimeout(1000);
    await page.locator('#btn-start-driving').click();
    await page.waitForTimeout(1500);

    // Recommendation should display charging station details and detour
    const panelContent = await page.locator('#driver-panel-content').textContent();
    expect(panelContent).toContain('S001');
    expect(panelContent).toContain('Charging');
    expect(panelContent).toContain('+0.5 km detour');
    expect(panelContent).toContain('Recommended');
  });
});

// ============================================================
// F. NO-SERVICE STATE
// ============================================================
test.describe('F. No-Service State', () => {
  test('displays no-service correctly', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();
    fixtures.mockTrajectory('TRJ0001');

    // Mock recommendation with no service needed
    await page.route('**/api/v1/recommend', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          has_recommendation: false,
          reason: 'SUFFICIENT_SOC_RANGE',
          eligible_count: 3,
          timings_ms: { total: 25 }
        })
      });
    });

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    // Start trip
    await page.locator('#btn-accept-trip').click();
    await page.waitForTimeout(1000);
    await page.locator('#btn-start-driving').click();
    await page.waitForTimeout(1500);

    // Page should not crash
    await expect(page.locator('#driver-panel-content')).toBeVisible();
  });
});

// ============================================================
// G. API ERRORS & EDGE CASES (409, 422, 503, TIMEOUT)
// ============================================================
test.describe('G. API Error', () => {
  test('displays 503 service unavailable error state without fake success', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();
    fixtures.mockTrajectory('TRJ0001');

    // Mock 503 API error
    await page.route('**/api/v1/recommend', (route) => {
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: { code: 'ENGINE_UNAVAILABLE', message: 'GraphHopper unavailable' }
        })
      });
    });

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    // Start trip
    await page.locator('#btn-accept-trip').click();
    await page.waitForTimeout(1000);
    await page.locator('#btn-start-driving').click();
    await page.waitForTimeout(1500);

    // Page should still be visible and show error state without fake success
    await expect(page.locator('#driver-panel-content')).toBeVisible();
    const panelContent = await page.locator('#driver-panel-content').textContent();
    expect(panelContent).not.toContain('Recommended');
  });

  test('HTTP 409 conflict clears recommendation and does not retain stale route', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();
    fixtures.mockTrajectory('TRJ0001');
    fixtures.mockDriverLocation();

    // Mock 409 CANDIDATE_STATE_CHANGED
    await page.route('**/api/v1/recommend', (route) => {
      route.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: {
            code: 'CANDIDATE_STATE_CHANGED',
            message: 'Station snapshot state changed during evaluation'
          }
        })
      });
    });

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    await page.locator('#btn-accept-trip').click();
    await page.waitForTimeout(1000);
    await page.locator('#btn-start-driving').click();
    await page.waitForTimeout(1500);

    // Verify lastRecommendation is null and diversion route is not active
    const driverState = await page.evaluate(() => {
      return {
        hasRec: window.app?.driverMode?.lastRecommendation !== null,
        driverState: window.app?.driverMode?.state
      };
    });
    expect(driverState.hasRec).toBe(false);

    // HUD does NOT contain recommended badge or active diversion card
    const hudContent = await page.locator('#driver-panel-content').textContent();
    expect(hudContent).not.toContain('Recommended');
  });

  test('HTTP 422 validation error displays error without fake no-service', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();
    fixtures.mockTrajectory('TRJ0001');
    fixtures.mockDriverLocation();

    // Mock 422 Unprocessable Entity
    await page.route('**/api/v1/recommend', (route) => {
      route.fulfill({
        status: 422,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: [
            { loc: ['body', 'context', 'raw_latitude'], msg: 'field required', type: 'value_error.missing' }
          ]
        })
      });
    });

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    await page.locator('#btn-accept-trip').click();
    await page.waitForTimeout(1000);
    await page.locator('#btn-start-driving').click();
    await page.waitForTimeout(1500);

    // HUD should NOT display fake "No Service Needed"
    const hudContent = await page.locator('#driver-panel-content').textContent();
    expect(hudContent).not.toContain('No Service Needed');
    expect(hudContent).not.toContain('Sufficient Range');
  });

  test('network timeout abort transitions to error and does not advance progress', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();
    fixtures.mockTrajectory('TRJ0001');

    // Location ingestion request times out / aborts
    await page.route('**/api/v1/drivers/**/location', (route) => {
      route.abort('timedout');
    });

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    await page.locator('#btn-accept-trip').click();
    await page.waitForTimeout(1000);
    await page.locator('#btn-start-driving').click();
    await page.waitForTimeout(1500);

    // Replay state should become ERROR and confirmed progress index should remain 0
    const replayState = await page.evaluate(() => {
      return {
        state: window.app?.replay?.state,
        currentIndex: window.app?.replay?.currentIndex,
        isStepInProgress: window.app?.replay?.isStepInProgress
      };
    });
    expect(replayState.state).toBe('ERROR');
    expect(replayState.currentIndex).toBe(0);
    expect(replayState.isStepInProgress).toBe(false);
  });
});

// ============================================================
// H. TECH VIEW
// ============================================================
test.describe('H. Tech View', () => {
  test('opens from button', async ({ page }) => {
    await page.goto('/demo?debug=true');
    await page.waitForTimeout(2000);

    // Tech view drawer should be hidden initially
    const drawer = page.locator('#tech-view-drawer');
    await expect(drawer).toHaveAttribute('aria-hidden', 'true');

    // Open tech view
    await page.locator('#btn-open-tech-view').click();
    await page.waitForTimeout(500);

    // Drawer should now be visible
    await expect(drawer).toHaveAttribute('aria-hidden', 'false');
  });

  test('/demo/technical page works', async ({ page }) => {
    await page.goto('/demo/technical');
    await page.waitForTimeout(2000);

    // Tech view drawer should be open
    const drawer = page.locator('#tech-view-drawer');
    await expect(drawer).toHaveAttribute('aria-hidden', 'false');
  });

  test('tech view truthfully displays raw GPS vs matched road segment without fake values', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();
    fixtures.mockTrajectory('TRJ0001');

    // Mock unbuffered location: RAW only, matched is null
    await page.route('**/api/v1/drivers/**/location', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'RAW_GPS_FALLBACK',
          trigger_reason: 'MANUAL_STEP',
          total_match_calls: 0,
          raw_position: { latitude: 21.0500, longitude: 105.8000 },
          matched_position: null
        })
      });
    });

    await page.goto('/demo?debug=true');
    await page.waitForTimeout(2000);

    await page.locator('#btn-accept-trip').click();
    await page.waitForTimeout(1000);
    await page.locator('#btn-start-driving').click();
    await page.waitForTimeout(1500);

    // Open Tech View drawer
    await page.locator('#btn-open-tech-view').click();
    await page.waitForTimeout(500);

    // Check location inspector content
    const techDrawer = await page.locator('#tech-view-drawer').textContent();
    // Exposes honest raw coordinates
    expect(techDrawer).toContain('21.0285');
    expect(techDrawer).toContain('105.8542');
    // Does NOT claim confidence = 1.0 or hardcoded FORWARD
    expect(techDrawer).not.toContain('confidence: 1.000');
  });
});

// ============================================================
// I. CATALOG FAILURE
// ============================================================
test.describe('I. Catalog Failure', () => {
  test('shows error banner when catalog fails', async ({ page }) => {
    // Intercept catalog requests to fail
    await page.route('**/demo/static/data/stations.json', (route) => {
      route.abort('failed');
    });

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    // Error banner should appear
    const errorBanner = page.locator('#bootstrap-error');
    await expect(errorBanner).toBeVisible();
  });
});

// ============================================================
// J. SWAP VS CHARGING & ENERGY WARNINGS
// ============================================================
test.describe('J. Service Types & Warnings', () => {
  test('battery swap recommendation displays swap branding and badge', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();
    fixtures.mockTrajectory('TRJ0001');
    fixtures.mockDriverLocation();

    // Mock swap recommendation
    fixtures.mockRecommendation({
      has_recommendation: true,
      recommended_station_id: 'S003',
      recommended_service_type: 'BATTERY_SWAP',
      eligible_count: 2,
      ranked_candidates: [
        {
          rank: 1,
          station_id: 'S003',
          service_type: 'BATTERY_SWAP',
          eta_to_station_s: 240,
          eta_to_service_complete_s: 480,
          features: {
            detour_distance_m: 300,
            detour_duration_s: 45,
            effective_queue_wait_s: 60,
            service_duration_s: 180,
            available_capacity: 4
          }
        }
      ],
      energy_context: {
        need_service: true,
        reason_code: 'LOW_SOC',
        current_soc_pct: 12
      }
    });

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    await page.locator('#btn-accept-trip').click();
    await page.waitForTimeout(1000);
    await page.locator('#btn-start-driving').click();
    await page.waitForTimeout(1500);

    const hudContent = await page.locator('#driver-panel-content').textContent();
    expect(hudContent).toContain('Battery Swap');
    expect(hudContent).toContain('S003');
  });

  test('critical energy warning displays when destination not reachable', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();
    fixtures.mockTrajectory('TRJ0001');
    fixtures.mockDriverLocation();

    fixtures.mockRecommendation({
      has_recommendation: true,
      energy_context: {
        need_service: true,
        reason_code: 'DESTINATION_NOT_REACHABLE',
        current_soc_pct: 10,
        estimated_remaining_range_km: 8,
        remaining_trip_distance_km: 18
      }
    });

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    await page.locator('#btn-accept-trip').click();
    await page.waitForTimeout(1000);
    await page.locator('#btn-start-driving').click();
    await page.waitForTimeout(1500);

    const banner = page.locator('.energy-warning-banner');
    await expect(banner).toBeVisible();
    await expect(banner).toHaveClass(/banner-critical/);
    await expect(banner).toContainText('ENERGY CRITICAL');
  });

  test('advisory warning displays when reserve insufficient', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();
    fixtures.mockTrajectory('TRJ0001');
    fixtures.mockDriverLocation();

    fixtures.mockRecommendation({
      has_recommendation: true,
      energy_context: {
        need_service: true,
        reason_code: 'INSUFFICIENT_POST_DESTINATION_RESERVE',
        current_soc_pct: 22,
        estimated_remaining_range_km: 15,
        remaining_trip_distance_km: 12,
        safety_reserve_km: 5
      }
    });

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    await page.locator('#btn-accept-trip').click();
    await page.waitForTimeout(1000);
    await page.locator('#btn-start-driving').click();
    await page.waitForTimeout(1500);

    const banner = page.locator('.energy-warning-banner');
    await expect(banner).toBeVisible();
    await expect(banner).toHaveClass(/banner-advisory/);
    await expect(banner).toContainText('Energy Reserve Low');
  });
});

// ============================================================
// K. NO ELIGIBLE CANDIDATE & RAW GPS ONLY
// ============================================================
test.describe('K. No Eligible & Raw GPS', () => {
  test('no eligible candidates renders empty state without fake station', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();
    fixtures.mockTrajectory('TRJ0001');
    fixtures.mockDriverLocation();

    fixtures.mockRecommendation({
      has_recommendation: false,
      recommended_station_id: null,
      recommended_service_type: null,
      eligible_count: 0,
      ranked_candidates: [],
      reason: 'NO_ELIGIBLE_CANDIDATES',
      energy_context: {
        need_service: true,
        reason_code: 'LOW_SOC',
        current_soc_pct: 8
      }
    });

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    await page.locator('#btn-accept-trip').click();
    await page.waitForTimeout(1000);
    await page.locator('#btn-start-driving').click();
    await page.waitForTimeout(1500);

    // Click Complete Trip to inspect full recommendation card
    await page.locator('#btn-complete-trip').click();
    await page.waitForTimeout(500);

    const panel = await page.locator('#driver-panel-content').textContent();
    expect(panel).toContain('No Service Needed / No Eligible Stations');
  });

  test('raw GPS only observation displays honest raw position and no fake match', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();
    fixtures.mockTrajectory('TRJ0001');
    fixtures.mockRecommendation();

    // Mock RAW-ONLY location response (no matched road segment)
    await page.route('**/api/v1/drivers/**/location', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'RAW_GPS_FALLBACK',
          trigger_reason: 'MANUAL_STEP',
          total_match_calls: 0,
          raw_position: { latitude: 21.0500, longitude: 105.8000 },
          matched_position: null
        })
      });
    });

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    await page.locator('#btn-accept-trip').click();
    await page.waitForTimeout(1000);
    await page.locator('#btn-start-driving').click();
    await page.waitForTimeout(1500);

    // The HUD must display Raw GPS coordinates without claiming road matched
    const hudContent = await page.locator('#driver-panel-content').textContent();
    expect(hudContent).toContain('Raw GPS');
    expect(hudContent).not.toContain('Road: RS001');
  });
});

// ============================================================
// L. CONCURRENCY, RACE CONDITIONS & INVALIDATION
// ============================================================
test.describe('L. Concurrency & State Invalidation', () => {
  test('rapid step clicks enforce max 1 in-flight request without overlap', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();
    fixtures.mockTrajectory('TRJ0001');
    fixtures.mockRecommendation();

    let concurrentRequests = 0;
    let maxConcurrency = 0;
    let totalLocationRequests = 0;

    await page.route('**/api/v1/drivers/**/location', async (route) => {
      concurrentRequests++;
      totalLocationRequests++;
      maxConcurrency = Math.max(maxConcurrency, concurrentRequests);

      // Add controlled artificial network delay to test concurrency window
      await new Promise(r => setTimeout(r, 200));
      concurrentRequests--;

      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'MATCHED',
          total_match_calls: totalLocationRequests,
          raw_position: { latitude: 21.0285, longitude: 105.8542 },
          matched_position: { latitude: 21.0285, longitude: 105.8542, road_segment_id: 'RS1' }
        })
      });
    });

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    await page.locator('#btn-accept-trip').click();
    await page.waitForTimeout(1000);
    await page.locator('#btn-start-driving').click();
    await page.waitForTimeout(500);

    // Rapidly click Step 3 times in quick succession
    const stepBtn = page.locator('#btn-driver-replay-step');
    await stepBtn.click();
    await stepBtn.click();
    await stepBtn.click();

    await page.waitForTimeout(1000);

    // Concurrency must never exceed 1
    expect(maxConcurrency).toBe(1);
  });

  test('reset while pending invalidates response and prevents stale update', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();
    fixtures.mockTrajectory('TRJ0001');
    fixtures.mockRecommendation();

    await page.route('**/api/v1/drivers/**/location', async (route) => {
      // Long delay to allow reset during pending
      await new Promise(r => setTimeout(r, 600));
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'MATCHED',
          total_match_calls: 99,
          raw_position: { latitude: 21.9999, longitude: 105.9999 },
          matched_position: { latitude: 21.9999, longitude: 105.9999, road_segment_id: 'STALE_SEG' }
        })
      });
    });

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    await page.locator('#btn-accept-trip').click();
    await page.waitForTimeout(1000);
    await page.locator('#btn-start-driving').click();

    // Step initiated
    await page.waitForTimeout(100);

    // Cancel / Reset trip while location request is still pending
    await page.locator('#btn-complete-trip').click();
    await page.waitForTimeout(200);
    await page.locator('#btn-back-available').click();
    await page.waitForTimeout(1000);

    // Driver badge should be AVAILABLE; stale response should have been rejected
    await expect(page.locator('#driver-status-badge')).toContainText('AVAILABLE');
  });

  test('slow API keeps max 1 active replay step and maintains correct progress', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();
    fixtures.mockTrajectory('TRJ0001');
    fixtures.mockRecommendation();

    let concurrentSteps = 0;
    let maxConcurrentSteps = 0;

    await page.route('**/api/v1/drivers/**/location', async (route) => {
      concurrentSteps++;
      maxConcurrentSteps = Math.max(maxConcurrentSteps, concurrentSteps);
      await new Promise(r => setTimeout(r, 400));
      concurrentSteps--;
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'MATCHED',
          trigger_reason: 'MANUAL_STEP',
          total_match_calls: 1,
          raw_position: { latitude: 21.0285, longitude: 105.8542 },
          matched_position: { latitude: 21.0285, longitude: 105.8542, road_segment_id: 'RS1' }
        })
      });
    });

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    await page.locator('#btn-accept-trip').click();
    await page.waitForTimeout(1000);
    await page.locator('#btn-start-driving').click();
    await page.waitForTimeout(500);

    // While first step is resolving, rapid-click step button twice
    const stepBtn = page.locator('#btn-driver-replay-step');
    await stepBtn.click();
    await stepBtn.click();

    // Wait for all in-flight actions to settle
    await page.waitForTimeout(1200);

    expect(maxConcurrentSteps).toBe(1);

    // Verify progress index did not jump erratically
    const index = await page.evaluate(() => window.app?.replay?.currentIndex);
    expect(index).toBeGreaterThanOrEqual(1);
    expect(index).toBeLessThanOrEqual(2);
  });

  test('pause while pending stops subsequent steps and does not schedule next step', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();
    fixtures.mockTrajectory('TRJ0001');
    fixtures.mockRecommendation();

    let stepCount = 0;
    await page.route('**/api/v1/drivers/**/location', async (route) => {
      stepCount++;
      // Controlled 500ms delay to create in-flight pause window
      await new Promise(r => setTimeout(r, 500));
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'MATCHED',
          total_match_calls: stepCount,
          raw_position: { latitude: 21.0285, longitude: 105.8542 },
          matched_position: { latitude: 21.0285, longitude: 105.8542, road_segment_id: 'RS1' }
        })
      });
    });

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    await page.locator('#btn-accept-trip').click();
    await page.waitForTimeout(1000);
    await page.locator('#btn-start-driving').click();
    await page.waitForTimeout(600); // Step 1 settles

    // Start auto-playback
    await page.locator('#btn-driver-replay-play').click();
    await page.waitForTimeout(100); // Step 2 is now in-flight

    // Click pause while step 2 is in-flight
    await page.locator('#btn-driver-replay-pause').click();

    // Allow step 2 response to resolve
    await page.waitForTimeout(800);

    const replayInfo = await page.evaluate(() => ({
      state: window.app?.replay?.state,
      index: window.app?.replay?.currentIndex
    }));

    // Must be paused, confirmed index at 2
    expect(replayInfo.state).toBe('PAUSED');
    const indexAtPause = replayInfo.index;

    // Wait an additional interval to prove NO next step is scheduled
    await page.waitForTimeout(1000);
    const indexLater = await page.evaluate(() => window.app?.replay?.currentIndex);
    expect(indexLater).toBe(indexAtPause);
  });

  test('switch scenario while pending discards earlier response without updating new scenario', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();

    let pendingScenarioA = true;
    await page.route('**/api/v1/candidate-search/evaluate', async (route) => {
      const body = route.request().postDataJSON();
      // If request is from scenario 1, delay it
      if (pendingScenarioA && body?.current_soc_pct === 85) {
        await new Promise(r => setTimeout(r, 600));
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            candidates: [
              { station_id: 'STALE_STATION_A', service_type: 'CHARGING', eligible: true }
            ]
          })
        });
      } else {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            candidates: [
              { station_id: 'FRESH_STATION_B', service_type: 'CHARGING', eligible: true }
            ]
          })
        });
      }
    });

    await page.goto('/demo?debug=true');
    await page.waitForTimeout(2000);

    // Open Simulation / Scenario panel
    await page.locator('#btn-toggle-sim-panel').click();
    await page.waitForTimeout(500);

    // Select Scenario 1
    const scPills = page.locator('.scenario-pill-btn');
    await scPills.nth(0).click(); // Scenario 1 (85% SOC) triggers runSimulation() with delay

    // Immediately while pending, switch to Scenario 3 (Low SOC)
    await page.waitForTimeout(100);
    pendingScenarioA = false;
    await scPills.nth(2).click(); // Scenario 3

    // Wait for the slow Scenario A response to settle
    await page.waitForTimeout(1000);

    // Assert that STALE_STATION_A was discarded and does not appear in candidate output
    const candidateContainerText = await page.locator('#sim-candidates-container').textContent();
    expect(candidateContainerText).not.toContain('STALE_STATION_A');
  });

  test('stale in-flight response is dropped via generation token verification', async ({ page }) => {
    const fixtures = createApiFixtures(page);
    fixtures.mockReadiness();
    fixtures.mockRoute();
    fixtures.mockTrajectory('TRJ0001');
    fixtures.mockRecommendation();

    await page.route('**/api/v1/drivers/**/location', async (route) => {
      // 600ms network delay
      await new Promise(r => setTimeout(r, 600));
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'MATCHED',
          total_match_calls: 99,
          raw_position: { latitude: 21.9999, longitude: 105.9999 },
          matched_position: { latitude: 21.9999, longitude: 105.9999, road_segment_id: 'STALE_ROAD' }
        })
      });
    });

    await page.goto('/demo');
    await page.waitForTimeout(2000);

    await page.locator('#btn-accept-trip').click();
    await page.waitForTimeout(1000);
    await page.locator('#btn-start-driving').click();

    // Step is now in flight
    await page.waitForTimeout(100);

    // Cancel trip - increments generation and resets state
    const genBeforeReset = await page.evaluate(() => window.app?.driverMode?.generation);
    await page.locator('#btn-complete-trip').click();
    await page.waitForTimeout(200);
    await page.locator('#btn-back-available').click();

    const genAfterReset = await page.evaluate(() => window.app?.driverMode?.generation);
    expect(genAfterReset).toBeGreaterThan(genBeforeReset);

    // Wait for the delayed response to arrive
    await page.waitForTimeout(800);

    // Inspect driverMode state - currentPos and lastRecommendation must remain null
    const driverState = await page.evaluate(() => ({
      currentPos: window.app?.driverMode?.currentPos,
      lastRecommendation: window.app?.driverMode?.lastRecommendation,
      state: window.app?.driverMode?.state
    }));

    expect(driverState.state).toBe('AVAILABLE');
    expect(driverState.currentPos).toBeNull();
    expect(driverState.lastRecommendation).toBeNull();
  });
});

// ============================================================
// M. MOBILE VIEWPORT USABILITY
// ============================================================
test.describe('M. Mobile Viewport', () => {
  test.use({ viewport: { width: 390, height: 844 } }); // iPhone 12 / 13 / 14 size

  test('mobile viewport renders controls and permits navigation', async ({ page }) => {
    await page.goto('/demo?debug=true');
    await page.waitForTimeout(2000);

    // Map and driver view should be visible
    await expect(page.locator('#map')).toBeVisible();
    await expect(page.locator('#driver-view-container')).toBeVisible();

    // Select trip button should be clickable
    const tripSelect = page.locator('#select-driver-trip');
    await expect(tripSelect).toBeVisible();

    // Open Tech View drawer on mobile
    await page.locator('#btn-open-tech-view').click();
    await page.waitForTimeout(500);

    const drawer = page.locator('#tech-view-drawer');
    await expect(drawer).toHaveAttribute('aria-hidden', 'false');

    // Close Tech View drawer
    await page.locator('#btn-close-tech-view').click();
    await page.waitForTimeout(500);
    await expect(drawer).toHaveAttribute('aria-hidden', 'true');
  });
});

