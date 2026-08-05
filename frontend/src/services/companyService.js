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
 * Get a single company's full intelligence profile plus the
 * deterministic match against the latest uploaded resume.
 * @param {string} companyName - Company name as it appears in the seed
 * @returns {Promise} Promise resolving to { company, match }
 */
export const getCompany = async (companyName) => {
  return api.get(`/api/companies/${encodeURIComponent(companyName)}`)
}

/**
 * Research a specific company
 * @param {number} id - Company ID
 * @returns {Promise} Promise with research result
 */
export const researchCompany = async (id) => {
  return api.post(`/api/companies/${id}/research`)
}
