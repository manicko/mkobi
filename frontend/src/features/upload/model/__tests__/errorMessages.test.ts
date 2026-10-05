import { describe, it, expect } from 'vitest'
import { ErrorCode } from '../../../../shared/types/enums'
import { uploadErrorMessages } from '../errorMessages'

describe('uploadErrorMessages', () => {
  it('contains all required upload error codes', () => {
    expect(uploadErrorMessages[ErrorCode.FILE_UPLOAD_ERROR]).toBe('Failed to upload file. Please try again.')
    expect(uploadErrorMessages[ErrorCode.FILE_TOO_LARGE]).toBe('File size exceeds the allowed limit (maximum 100 MB)')
    expect(uploadErrorMessages[ErrorCode.INVALID_FILE_TYPE]).toBe('Invalid file type. Only CSV and GZIP files are allowed.')
    expect(uploadErrorMessages[ErrorCode.FILE_PROCESSING_ERROR]).toBe('File processing error. Please check the data format.')
    expect(uploadErrorMessages[ErrorCode.PROCESSING_FAILED]).toBe('Failed to process file. Please contact the administrator.')
    expect(uploadErrorMessages[ErrorCode.PROCESSING_IN_PROGRESS]).toBe('File is already being processed. Please wait for completion.')
  })
})
