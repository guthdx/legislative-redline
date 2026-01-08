import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import Analysis from './pages/Analysis'
import Comparison from './pages/Comparison'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/analysis/:documentId" element={<Analysis />} />
        <Route path="/comparison/:documentId" element={<Comparison />} />
      </Routes>
    </Layout>
  )
}

export default App
