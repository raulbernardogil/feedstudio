import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { EmptyState } from './components/ui'
import { CatalogPage } from './features/catalog/CatalogPage'
import { ChannelsPage } from './features/channels/ChannelsPage'
import { DashboardPage } from './features/dashboard/DashboardPage'
import { JobsPage } from './features/jobs/JobsPage'
import { PreviewPage } from './features/preview/PreviewPage'
import { RulesPage } from './features/rules/RulesPage'
import { SettingsPage } from './features/settings/SettingsPage'
import { SourcesPage } from './features/sources/SourcesPage'
import { ValidationPage } from './features/validation/ValidationPage'
import { ApiError } from './lib/api'
import { WorkspaceProvider } from './lib/workspace'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
      refetchOnWindowFocus: false,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <WorkspaceProvider>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<DashboardPage />} />
              <Route path="sources" element={<SourcesPage />} />
              <Route path="catalog" element={<CatalogPage />} />
              <Route path="rules" element={<RulesPage />} />
              <Route path="preview" element={<PreviewPage />} />
              <Route path="validation" element={<ValidationPage />} />
              <Route path="channels" element={<ChannelsPage />} />
              <Route path="jobs" element={<JobsPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="*" element={<EmptyState title="Página no encontrada" />} />
            </Route>
          </Routes>
        </WorkspaceProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
