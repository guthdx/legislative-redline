import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import FileUpload from '../components/FileUpload'
import { documentApi } from '../services/api'

function Home() {
  const navigate = useNavigate()
  const [error, setError] = useState(null)

  const uploadMutation = useMutation({
    mutationFn: documentApi.upload,
    onSuccess: (data) => {
      navigate(`/analysis/${data.id}`)
    },
    onError: (err) => {
      setError(err.response?.data?.detail || 'Failed to upload document')
    },
  })

  const handleFileSelect = (file) => {
    setError(null)
    uploadMutation.mutate(file)
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          Legislative Redline Tool
        </h1>
        <p className="text-gray-600">
          Compare proposed statutory amendments against current USC and CFR text
        </p>
      </div>

      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Upload Document
        </h2>

        <FileUpload
          onFileSelect={handleFileSelect}
          isUploading={uploadMutation.isPending}
        />

        {error && (
          <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
          </div>
        )}

        <div className="mt-6 text-sm text-gray-500">
          <h3 className="font-medium text-gray-700 mb-2">How it works:</h3>
          <ol className="list-decimal list-inside space-y-1">
            <li>Upload a PDF or DOCX containing proposed amendments</li>
            <li>We detect all USC and CFR citations in the document</li>
            <li>Current statutory text is fetched from official sources</li>
            <li>View a side-by-side comparison with redlined changes</li>
          </ol>
        </div>
      </div>

      <div className="mt-8 grid grid-cols-2 gap-4">
        <div className="bg-blue-50 rounded-lg p-4">
          <h3 className="font-medium text-blue-900 mb-1">USC Support</h3>
          <p className="text-sm text-blue-700">
            United States Code sections via govinfo.gov
          </p>
        </div>
        <div className="bg-green-50 rounded-lg p-4">
          <h3 className="font-medium text-green-900 mb-1">CFR Support</h3>
          <p className="text-sm text-green-700">
            Code of Federal Regulations via eCFR.gov
          </p>
        </div>
      </div>
    </div>
  )
}

export default Home
