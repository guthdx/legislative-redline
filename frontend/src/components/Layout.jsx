function Layout({ children }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <a href="/" className="flex items-center space-x-2">
              <svg className="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span className="text-xl font-semibold text-gray-900">Legislative Redline</span>
            </a>
            <nav className="flex items-center space-x-4">
              <a href="/" className="text-gray-600 hover:text-gray-900">Upload</a>
            </nav>
          </div>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-4 py-8">
        {children}
      </main>
      <footer className="border-t bg-white mt-auto">
        <div className="max-w-7xl mx-auto px-4 py-4 text-center text-sm text-gray-500">
          Compare proposed amendments against USC and CFR
        </div>
      </footer>
    </div>
  )
}

export default Layout
