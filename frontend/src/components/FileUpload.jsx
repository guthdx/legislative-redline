import { useCallback } from 'react'
import { useDropzone } from 'react-dropzone'

function FileUpload({ onFileSelect, isUploading }) {
  const onDrop = useCallback((acceptedFiles) => {
    if (acceptedFiles.length > 0) {
      onFileSelect(acceptedFiles[0])
    }
  }, [onFileSelect])

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/msword': ['.doc'],
    },
    maxFiles: 1,
    disabled: isUploading,
  })

  return (
    <div
      {...getRootProps()}
      className={`dropzone ${isDragActive ? 'dropzone-active' : ''} ${isDragReject ? 'dropzone-reject' : ''} ${isUploading ? 'opacity-50 cursor-not-allowed' : ''}`}
    >
      <input {...getInputProps()} />
      <div className="space-y-4">
        <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
        </svg>
        {isUploading ? (
          <p className="text-gray-600">Uploading...</p>
        ) : isDragActive ? (
          <p className="text-blue-600">Drop the file here...</p>
        ) : (
          <>
            <p className="text-gray-600">
              <span className="text-blue-600 font-medium">Click to upload</span> or drag and drop
            </p>
            <p className="text-sm text-gray-500">PDF or DOCX containing proposed statutory amendments</p>
          </>
        )}
      </div>
    </div>
  )
}

export default FileUpload
