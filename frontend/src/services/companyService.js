import api from './api'

/**
 * Discover newly funded companies
 * @param {Object} options - Discovery options
 * @returns {Promise} Promise with discovery result
 */
export const discoverCompanies = async (options = {}) => {
  return api.post('/api/companies/discover', options)
}

/**
 * Get list of companies
 * @param {Object} params - Query parameters
 * @returns {Promise} Promise with companies list
 */
export const getCompanies = async (params = {}) => {
  return api.get('/api/companies', { params })
}

/**
 * Sprint 14.1 — fetch the full list (including the per-company
 * ``recommendation.intelligence`` block). The detail endpoint
 * ``GET /api/companies/{name}`` does not return this block, so
 * the detail page does a second list call and looks up the one
 * company by name. Returns the raw companies array (or []).
 */
export const getCompaniesIntelligence = async (params = {}) => {
  const res = await api.get('/api/companies', { params })
  return Array.isArray(res.data?.companies) ? res.data.companies : []
}

/**
 * Get a single company's full intelligence profile plus the
 * deterministic match against the latest uploaded resume.
 * @param {string} companyName - Company name as it appears in the seed
 * @returns {Promise} Promise resolving to { company, match }
 */
export const getCompany = async (companyName) => {
  return api.get(`/api/companies/${encodeURIComponent(companyName)}`)
}
