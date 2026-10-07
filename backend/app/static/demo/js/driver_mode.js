// Stable cockpit entry point. The browser app remains responsible for startup.
export { DriverModeController } from './ui/driver_controller.js';
export {
    DriverState,
    isValidStateTransition,
    getDriverStateLabel,
    getDriverStateBadgeClass
} from './domain/driver_state.js';
export {
    straightLineDistanceKm,
    EARTH_RADIUS_KM,
    FALLBACK_MODEL_SPECS,
    MODEL_SPECS,
    VINFAST_MODEL_SPECS,
    registerVehicleModel,
    getVehicleModelSpec,
    calculateEstimatedRangeKm,
    calculateSocDepletion
} from './domain/vehicle_model.js';
