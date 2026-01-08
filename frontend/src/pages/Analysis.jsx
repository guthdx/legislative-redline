import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import CitationList from '../components/CitationList'
import { documentApi, citationApi } from '../services/api'

function Analysis() {
  const { documentId } = useParams()
  const navigate = useNavigate()
  const [fetchingCitations, setFetchingCitations] = useState([])

  // Parse document and detect citations
  const parseMutation = useMutation({
    mutationFn: () => documentApi.parse(documentId),
    onSuccess: () => {
      citationsQuery.refetch()
    },
  })

  // Get citations
  const citationsQuery = useQuery({
    queryKey: ['citations', documentId],
    queryFn: () => documentApi.getCitations(documentId),
    enabled: !!documentId,
  })

  // Fetch individual statute
  const handleFetchStatute = async (citationId) => {
    setFetchingCitations((prev) => [...prev, citationId])
    try {
      await citationApi.fetchStatute(citationId)
      citationsQuery.refetch()
    } catch (err) {
      console.error('Failed to fetch statute:', err)
    } finally {
      setFetchingCitations((prev) => prev.filter((id) => id !== citationId))
    }
  }

  // Generate comparison
  const compareMutation = useMutation({
    mutationFn: () => documentApi.compare(documentId),
    onSuccess: () => {
      navigate(`/comparison/${documentId}`)
    },
  })

  const citations = citationsQuery.data?.citations || []
  const allFetched = citations.length > 0 && citations.every((c) => c.statute_fetched)

  // Auto-parse on mount if not yet parsed
  if (!parseMutation.isPending && !parseMutation.isSuccess && !citationsQuery.data) {
    parseMutation.mutate()
  }

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Citation Analysis</h1>
          <p className="text-gray-600">
            {citations.length} citation{citations.length !== 1 ? 's' : ''} detected
          </p>
        </div>
        <button
          onClick={() => navigate('/')}
          className="text-gray-500 hover:text-gray-700"
        >
          Upload New
        </button>
      </div>

      {parseMutation.isPending && (
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Parsing document and detecting citations...</p>
        </div>
      )}

      {citationsQuery.isLoading && !parseMutation.isPending && (
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading citations...</p>
        </div>
      )}

      {citations.length > 0 && (
        <>
          <div className="bg-white rounded-lg shadow-sm border mb-6">
            <div className="p-4 border-b bg-gray-50">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold text-gray-900">Detected Citations</h2>
                <button
                  onClick={() => {
                    citations.forEach((c) => {
                      if (!c.statute_fetched) {
                        handleFetchStatute(c.id)
                      }
                    })
                  }}
                  disabled={allFetched || fetchingCitations.length > 0}
                  className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                >
                  Fetch All
                </button>
              </div>
            </div>
            <div className="p-4">
              <CitationList
                citations={citations}
                onFetchStatute={handleFetchStatute}
                fetchingCitations={fetchingCitations}
              />
            </div>
          </div>

          <div className="text-center">
            <button
              onClick={() => compareMutation.mutate()}
              disabled={!allFetched || compareMutation.isPending}
              className="px-6 py-3 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {compareMutation.isPending ? 'Generating...' : 'Generate Redline Comparison'}
            </button>
            {!allFetched && (
              <p className="mt-2 text-sm text-gray-500">
                Fetch all statutes before generating comparison
              </p>
            )}
          </div>
        </>
      )}

      {citations.length === 0 && !parseMutation.isPending && !citationsQuery.isLoading && (
        <div className="text-center py-12 bg-white rounded-lg border">
          <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <h3 className="mt-4 text-lg font-medium text-gray-900">No citations found</h3>
          <p className="mt-2 text-gray-500">
            We couldn't detect any USC or CFR citations in this document.
          </p>
          <button
            onClick={() => navigate('/')}
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Try Another Document
          </button>
        </div>
      )}
    </div>
  )
}

export default Analysis
