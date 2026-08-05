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

/**
 * Get a previously generated document
 * @param {number} id - Document ID
 * @returns {Promise} Promise with document content
 */
export const getDocument = async (id) => {
  return api.get(`/api/documents/${id}`)
}

/**
 * Download a generated document
 * @param {number} id - Document ID
 * @returns {Promise} Promise with document file
 */
export const downloadDocument = async (id) => {
  return api.get(`/api/documents/${id}/download`, {
    responseType: 'blob',
  })
}
