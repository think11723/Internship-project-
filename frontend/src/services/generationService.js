import api from './api'

/**
 * Generate a personalized cover letter for a specific company.
 * Calls the existing POST /api/documents/generate endpoint.
 * @param {string} companyName - Company name as it appears in the seed
 * @returns {Promise} Promise resolving to { company, content }
 */
export const generateCoverLetter = async (companyName) => {
  return api.post('/api/documents/generate', { company_name: companyName })
}
