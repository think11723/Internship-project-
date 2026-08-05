import api from './api'

/**
 * Generate the weekly career intelligence report.
 * Triggers the backend orchestration workflow which coordinates
 * resume, discovery, research, matching, generation, and report services.
 *
 * @returns {Promise} Promise resolving to the weekly report payload:
 *   { summary, generated_at, companies_found, top_matches: [...] }
 */
export const generateWeeklyReport = async () => {
  return api.post('/api/workflow/weekly-report')
}