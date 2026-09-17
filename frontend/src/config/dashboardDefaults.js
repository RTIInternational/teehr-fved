/**
 * Dashboard default configuration settings
 *
 * These settings control the default selections when the dashboard loads.
 * Update these values as new configurations become available.
 */

export const FORECAST_DASHBOARD_DEFAULTS = {
  // Preferred default configuration for forecasts
  preferredConfiguration: 'nwm30_medium_range',

  // Preferred default variable
  preferredVariable: 'streamflow_hourly_inst',

  // Default metric for map coloring
  defaultMetricName: 'relative_bias',
};

/**
 * Helper function to select the best default from available options
 * @param {string|null} preferred - The preferred default value
 * @param {Array} available - Array of available options
 * @returns {string|null} The selected default
 */
export const selectDefault = (preferred, available) => {
  if (!Array.isArray(available) || available.length === 0) {
    return null;
  }

  // If preferred value exists in available options, use it
  if (preferred !== undefined && available.includes(preferred)) {
    return preferred;
  }

  // Otherwise fall back to first available option
  return available[0];
};
