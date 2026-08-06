// Sprint 14.4 — Career Plan service.
// Thin wrapper around GET /api/career-plan. The backend aggregates
// the latest resume + cached company list and returns the planner
// output. See backend/app/api/routes/career.py for the route.
//
// On the no-resume path the response carries ``requires_resume: true``,
// so the caller can render the standard empty-state UX without a
// separate status check.

import api from './api'

/**
 * Fetch the aggregated Career Plan from the backend.
 *
 * @returns {Promise<Object>} The plan payload. Shape:
 *   {
 *     requires_resume: boolean,
 *     message?: string,
 *     weekly_goal: string,
 *     today_tasks: Array<string | {day, action}>,
 *     this_week_tasks: Array<string | {day, action}>,
 *     resume_improvements: Array<string>,
 *     interview_preparation: Array<string>,
 *     networking_tasks: Array<string>,
 *     follow_up_plan: Array<string>,
 *     high_priority_companies: Array<string>,
 *     medium_priority_companies: Array<string>,
 *     long_term_targets: Array<string>,
 *     estimated_hours_required: number,
 *     portfolio: {
 *       text, high_priority_count, medium_priority_count,
 *       long_term_count, total_companies,
 *       average_opportunity_score, highest_opportunity_score,
 *       average_resume_match, resume_uploaded,
 *     },
 *     next_action: string,
 *     resume_uploaded?: boolean,
 *   }
 */
export const getCareerPlan = async () => {
  const res = await api.get('/api/career-plan')
  return res.data || {}
}
