import { useState } from 'react'

/**
 * Parse diff_html to create highlighted versions for side-by-side view
 * Original: shows text with deletions highlighted (red strikethrough)
 * Amended: shows text with insertions highlighted (green)
 */
function parseDiffForSideBySide(diffHtml, originalText, amendedText) {
  // Extract the content from redline-content div if present
  let content = diffHtml
  const contentMatch = diffHtml.match(/<div class="redline-content">([\s\S]*?)<\/div>/)
  if (contentMatch) {
    content = contentMatch[1]
  }

  // For Original view: show deletions with red background, remove insertions
  const originalHighlighted = content
    // Keep del tags but style them
    .replace(/<del[^>]*>/g, '<span class="bg-red-200 text-red-800 line-through px-0.5">')
    .replace(/<\/del>/g, '</span>')
    // Remove ins tags and their content for original view
    .replace(/<ins[^>]*>[\s\S]*?<\/ins>/g, '')

  // For Amended view: show insertions with green background, remove deletions
  const amendedHighlighted = content
    // Keep ins tags but style them
    .replace(/<ins[^>]*>/g, '<span class="bg-green-200 text-green-800 font-semibold px-0.5">')
    .replace(/<\/ins>/g, '</span>')
    // Remove del tags and their content for amended view
    .replace(/<del[^>]*>[\s\S]*?<\/del>/g, '')

  return { originalHighlighted, amendedHighlighted }
}

/**
 * Check if diff has actual changes (contains del or ins tags)
 */
function hasChanges(diffHtml) {
  return diffHtml && (diffHtml.includes('<del') || diffHtml.includes('<ins'))
}

function RedlineViewer({ comparisons }) {
  const [viewMode, setViewMode] = useState('inline') // 'inline' or 'side-by-side'
  const [expandedId, setExpandedId] = useState(null)

  if (!comparisons || comparisons.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        No comparisons available yet.
      </div>
    )
  }

  // Separate comparisons with and without changes
  const withChanges = comparisons.filter(c => hasChanges(c.diff_html))
  const withoutChanges = comparisons.filter(c => !hasChanges(c.diff_html))

  return (
    <div className="space-y-6">
      {/* View Mode Toggle */}
      <div className="flex justify-between items-center">
        <div className="text-sm text-gray-600">
          <span className="font-medium text-green-700">{withChanges.length}</span> with changes,
          <span className="ml-1 text-gray-500">{withoutChanges.length}</span> unchanged
        </div>
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

      {/* Legend */}
      <div className="flex items-center justify-center space-x-6 text-sm bg-gray-50 py-3 rounded-lg border">
        <div className="flex items-center space-x-2">
          <span className="px-2 py-0.5 bg-red-200 text-red-800 line-through rounded text-xs">deleted</span>
          <span className="text-gray-600">Struck text</span>
        </div>
        <div className="flex items-center space-x-2">
          <span className="px-2 py-0.5 bg-green-200 text-green-800 font-semibold rounded text-xs">inserted</span>
          <span className="text-gray-600">New text</span>
        </div>
      </div>

      {/* Comparisons WITH changes */}
      {withChanges.length > 0 && (
        <div className="space-y-4">
          <h3 className="font-semibold text-gray-900 flex items-center">
            <span className="w-2 h-2 bg-green-500 rounded-full mr-2"></span>
            Sections with Changes ({withChanges.length})
          </h3>
          {withChanges.map((comparison) => {
            const { originalHighlighted, amendedHighlighted } = parseDiffForSideBySide(
              comparison.diff_html,
              comparison.original_text,
              comparison.amended_text
            )

            return (
              <div key={comparison.id} className="bg-white border-2 border-green-200 rounded-lg overflow-hidden shadow-sm">
                <div className="bg-green-50 px-4 py-3 border-b border-green-200">
                  <div className="flex items-center justify-between">
                    <h3 className="font-medium text-gray-900">{comparison.citation_text}</h3>
                    <span className="px-2 py-1 bg-green-100 text-green-800 text-xs rounded-full font-medium">
                      Has Changes
                    </span>
                  </div>
                  {comparison.amendment_type && (
                    <span className="text-sm text-gray-600">
                      Amendment type: <span className="font-medium">{comparison.amendment_type.replace('_', ' ')}</span>
                    </span>
                  )}
                </div>

                {viewMode === 'inline' ? (
                  <div className="p-4">
                    <div
                      className="prose max-w-none text-sm leading-relaxed whitespace-pre-wrap"
                      dangerouslySetInnerHTML={{ __html: comparison.diff_html }}
                    />
                  </div>
                ) : (
                  <div className="grid grid-cols-2 divide-x divide-gray-200">
                    <div className="p-4 bg-red-50/30">
                      <h4 className="text-sm font-semibold text-red-700 mb-3 flex items-center">
                        <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Original (with deletions)
                      </h4>
                      <div
                        className="prose max-w-none text-sm leading-relaxed whitespace-pre-wrap"
                        dangerouslySetInnerHTML={{ __html: originalHighlighted }}
                      />
                    </div>
                    <div className="p-4 bg-green-50/30">
                      <h4 className="text-sm font-semibold text-green-700 mb-3 flex items-center">
                        <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v3m0 0v3m0-3h3m-3 0H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Amended (with insertions)
                      </h4>
                      <div
                        className="prose max-w-none text-sm leading-relaxed whitespace-pre-wrap"
                        dangerouslySetInnerHTML={{ __html: amendedHighlighted }}
                      />
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Comparisons WITHOUT changes */}
      {withoutChanges.length > 0 && (
        <div className="space-y-4">
          <h3 className="font-semibold text-gray-500 flex items-center">
            <span className="w-2 h-2 bg-gray-400 rounded-full mr-2"></span>
            Sections Without Changes ({withoutChanges.length})
          </h3>
          <div className="space-y-2">
            {withoutChanges.map((comparison) => (
              <div key={comparison.id} className="bg-white border border-gray-200 rounded-lg overflow-hidden">
                <button
                  onClick={() => setExpandedId(expandedId === comparison.id ? null : comparison.id)}
                  className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
                >
                  <div className="text-left">
                    <h3 className="font-medium text-gray-700">{comparison.citation_text}</h3>
                    <span className="text-sm text-gray-500">
                      {comparison.amendment_type === 'unknown'
                        ? 'Definitional reference'
                        : `${comparison.amendment_type?.replace('_', ' ')} - no matching text found`}
                    </span>
                  </div>
                  <svg
                    className={`w-5 h-5 text-gray-400 transition-transform ${expandedId === comparison.id ? 'rotate-180' : ''}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
                {expandedId === comparison.id && (
                  <div className="px-4 pb-4 border-t bg-gray-50">
                    <p className="text-xs text-gray-500 mt-2 mb-2">
                      This citation references the statute but no amendment pattern was detected or the text to modify wasn't found.
                    </p>
                    <div className="text-sm text-gray-600 max-h-48 overflow-y-auto bg-white p-3 rounded border">
                      {comparison.original_text?.substring(0, 500)}
                      {comparison.original_text?.length > 500 && '...'}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default RedlineViewer
