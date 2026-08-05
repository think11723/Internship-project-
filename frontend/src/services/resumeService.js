import api from './api'

/**
 * Upload and analyze resume
 * @param {File} file - Resume file (PDF)
 * @param {Object} options - { jobId, onUploadProgress }
 * @returns {Promise} Promise with analysis result
 */
export const uploadResume = async (file, options = {}) => {
  const { jobId, onUploadProgress } = options
  const formData = new FormData()
  formData.append('file', file)
  const config = {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  }
  if (jobId) config.headers['X-Upload-Id'] = jobId
  if (onUploadProgress) config.onUploadProgress = onUploadProgress
  return api.post('/api/resume/upload', formData, config)
}

/**
 * Get latest resume metadata (used by the "Current Resume" card)
 * @returns {Promise} Promise resolving to {id, original_filename, parsed_at, name, email, summary, skills_count, file_size, status}
 */
export const getResumeLatest = async () => {
  return api.get('/api/resume/latest')
}

/**
 * Get latest resume full analysis (used by "View Resume" action)
 * @returns {Promise} Promise resolving to a ResumeUploadResponse-shaped payload
 */
export const getResumeLatestAnalysis = async () => {
  return api.get('/api/resume/latest/analysis')
}

/**
 * Delete the latest resume + clear all derived state
 * @returns {Promise} Promise resolving to {success, deleted_id}
 */
export const deleteResumeLatest = async () => {
  return api.delete('/api/resume/latest')
}

/**
 * Poll the upload progress endpoint for real backend stage updates
 * @param {string} jobId - The X-Upload-Id passed to /upload
 * @returns {Promise} Promise resolving to {job_id, stage, status, updated_at, error, result}
 */
export const getUploadStatus = async (jobId) => {
  return api.get(`/api/resume/upload-status/${encodeURIComponent(jobId)}`)
}
