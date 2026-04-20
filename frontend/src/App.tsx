import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Navbar } from './components/layout/Navbar'
import { UploadPage } from './pages/UploadPage'
import { ProgressPage } from './pages/ProgressPage'
import { OutputPage } from './pages/OutputPage'
import { TemplatesPage } from './pages/TemplatesPage'
import { TemplatePreviewPage } from './pages/TemplatePreviewPage'

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-white">
        <Navbar />
        <Routes>
          <Route path="/"          element={<UploadPage />} />
          <Route path="/progress"  element={<ProgressPage />} />
          <Route path="/output"    element={<OutputPage />} />
          <Route path="/templates" element={<TemplatesPage />} />
          <Route path="/templates/:templateId/preview" element={<TemplatePreviewPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}
