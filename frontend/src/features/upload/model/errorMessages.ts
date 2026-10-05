import { ErrorCode } from '../../../shared/types/enums'
import { registerFeatureErrorMessages } from '../../../shared/api/errorSurfaces'

/**
 * Upload feature error message map with English strings.
 * Contains error codes specific to file upload and processing.
 */
export const uploadErrorMessages: Partial<Record<ErrorCode, string>> = {
  [ErrorCode.FILE_UPLOAD_ERROR]: 'Failed to upload file. Please try again.',
  [ErrorCode.FILE_TOO_LARGE]: 'File size exceeds the allowed limit (maximum 100 MB)',
  [ErrorCode.INVALID_FILE_TYPE]: 'Invalid file type. Only CSV and GZIP files are allowed.',
  [ErrorCode.FILE_PROCESSING_ERROR]: 'File processing error. Please check the data format.',
  [ErrorCode.PROCESSING_FAILED]: 'Failed to process file. Please contact the administrator.',
  [ErrorCode.PROCESSING_IN_PROGRESS]: 'File is already being processed. Please wait for completion.',
}

registerFeatureErrorMessages('upload', uploadErrorMessages)