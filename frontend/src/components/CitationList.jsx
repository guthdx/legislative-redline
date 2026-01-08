function CitationList({ citations, onFetchStatute, fetchingCitations }) {
  if (!citations || citations.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        No citations detected in the document.
      </div>
    )
  }

  const getTypeLabel = (type) => {
    switch (type) {
      case 'usc': return 'USC'
      case 'cfr': return 'CFR'
      case 'publaw': return 'Public Law'
      default: return type.toUpperCase()
    }
  }

  const getTypeBadgeColor = (type) => {
    switch (type) {
      case 'usc': return 'bg-blue-100 text-blue-800'
      case 'cfr': return 'bg-green-100 text-green-800'
      case 'publaw': return 'bg-purple-100 text-purple-800'
      default: return 'bg-gray-100 text-gray-800'
    }
  }

  return (
    <div className="space-y-3">
      {citations.map((citation) => (
        <div
          key={citation.id}
          className="bg-white border rounded-lg p-4 flex items-center justify-between"
        >
          <div className="flex items-center space-x-3">
            <span className={`px-2 py-1 text-xs font-medium rounded ${getTypeBadgeColor(citation.citation_type)}`}>
              {getTypeLabel(citation.citation_type)}
            </span>
            <span className="font-mono text-sm">{citation.raw_text}</span>
          </div>
          <div className="flex items-center space-x-2">
            {citation.statute_fetched ? (
              <span className="text-green-600 text-sm flex items-center">
                <svg className="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
                Fetched
              </span>
            ) : (
              <button
                onClick={() => onFetchStatute(citation.id)}
                disabled={fetchingCitations.includes(citation.id)}
                className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
              >
                {fetchingCitations.includes(citation.id) ? 'Fetching...' : 'Fetch'}
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

export default CitationList
