import { useState } from 'react'

function RedlineViewer({ comparisons }) {
  const [viewMode, setViewMode] = useState('inline') // 'inline' or 'side-by-side'

  if (!comparisons || comparisons.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        No comparisons available yet.
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* View Mode Toggle */}
      <div className="flex justify-end">
        <div className="inline-flex rounded-lg border border-gray-200 p-1 bg-white">
          <button
            onClick={() => setViewMode('inline')}
            className={`px-4 py-2 text-sm rounded-md transition-colors ${
              viewMode === 'inline'
                ? 'bg-blue-600 text-white'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            Inline
          </button>
          <button
            onClick={() => setViewMode('side-by-side')}
            className={`px-4 py-2 text-sm rounded-md transition-colors ${
              viewMode === 'side-by-side'
                ? 'bg-blue-600 text-white'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            Side by Side
          </button>
        </div>
      </div>

      {/* Comparisons */}
      {comparisons.map((comparison) => (
        <div key={comparison.id} className="bg-white border rounded-lg overflow-hidden">
          <div className="bg-gray-50 px-4 py-3 border-b">
            <h3 className="font-medium text-gray-900">{comparison.citation_text}</h3>
            {comparison.amendment_type && (
              <span className="text-sm text-gray-500">
                Amendment type: {comparison.amendment_type.replace('_', ' ')}
              </span>
            )}
          </div>

          {viewMode === 'inline' ? (
            <div className="p-4">
              <div
                className="prose max-w-none"
                dangerouslySetInnerHTML={{ __html: comparison.diff_html }}
              />
            </div>
          ) : (
            <div className="grid grid-cols-2 divide-x">
              <div className="p-4">
                <h4 className="text-sm font-medium text-gray-500 mb-2">Original</h4>
                <div className="prose max-w-none text-sm">
                  {comparison.original_text}
                </div>
              </div>
              <div className="p-4">
                <h4 className="text-sm font-medium text-gray-500 mb-2">Amended</h4>
                <div className="prose max-w-none text-sm">
                  {comparison.amended_text}
                </div>
              </div>
            </div>
          )}
        </div>
      ))}

      {/* Legend */}
      <div className="flex items-center justify-center space-x-6 text-sm text-gray-600">
        <div className="flex items-center space-x-2">
          <span className="w-4 h-4 bg-redline-deleted rounded"></span>
          <span>Deleted text</span>
        </div>
        <div className="flex items-center space-x-2">
          <span className="w-4 h-4 bg-redline-inserted rounded"></span>
          <span>Inserted text</span>
        </div>
      </div>
    </div>
  )
}

export default RedlineViewer
