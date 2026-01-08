import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import RedlineViewer from '../components/RedlineViewer'
import { documentApi } from '../services/api'

function Comparison() {
  const { documentId } = useParams()
  const navigate = useNavigate()

  const resultQuery = useQuery({
    queryKey: ['comparison', documentId],
    queryFn: () => documentApi.getResult(documentId),
    enabled: !!documentId,
  })

  const comparisons = resultQuery.data?.comparisons || []

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Redline Comparison</h1>
          <p className="text-gray-600">
            {comparisons.length} section{comparisons.length !== 1 ? 's' : ''} compared
          </p>
        </div>
        <div className="flex space-x-2">
          <button
            onClick={() => navigate(`/analysis/${documentId}`)}
            className="px-4 py-2 border rounded-lg text-gray-700 hover:bg-gray-50"
          >
            Back to Analysis
          </button>
          <button
            onClick={() => window.print()}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Print
          </button>
        </div>
      </div>

      {resultQuery.isLoading && (
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading comparison results...</p>
        </div>
      )}

      {resultQuery.isError && (
        <div className="text-center py-12 bg-red-50 rounded-lg border border-red-200">
          <p className="text-red-700">Failed to load comparison results.</p>
          <button
            onClick={() => resultQuery.refetch()}
            className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
          >
            Retry
          </button>
        </div>
      )}

      {!resultQuery.isLoading && !resultQuery.isError && (
        <RedlineViewer comparisons={comparisons} />
      )}

      {!resultQuery.isLoading && comparisons.length === 0 && !resultQuery.isError && (
        <div className="text-center py-12 bg-white rounded-lg border">
          <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <h3 className="mt-4 text-lg font-medium text-gray-900">No comparisons available</h3>
          <p className="mt-2 text-gray-500">
            The comparison hasn't been generated yet or no amendments were detected.
          </p>
          <button
            onClick={() => navigate(`/analysis/${documentId}`)}
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Go to Analysis
          </button>
        </div>
      )}
    </div>
  )
}

export default Comparison
