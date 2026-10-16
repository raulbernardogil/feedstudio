import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import type { Channel, Source } from './types'

interface Workspace {
  sources: Source[]
  channels: Channel[]
  sourceId: number | null
  channelId: number | null
  source: Source | null
  channel: Channel | null
  setSourceId: (id: number | null) => void
  setChannelId: (id: number | null) => void
  loading: boolean
}

const WorkspaceContext = createContext<Workspace | null>(null)

function stored(key: string): number | null {
  const v = localStorage.getItem(key)
  return v ? Number(v) : null
}

/** Keeps the selected source/channel across pages (persisted per browser). */
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [sourceId, setSourceIdState] = useState<number | null>(() => stored('feedstudio.source'))
  const [channelId, setChannelIdState] = useState<number | null>(() => stored('feedstudio.channel'))
  const sourcesQuery = useQuery({ queryKey: ['sources'], queryFn: api.sources })
  const channelsQuery = useQuery({ queryKey: ['channels'], queryFn: () => api.channels() })
  const sources = useMemo(() => sourcesQuery.data?.items ?? [], [sourcesQuery.data])
  const allChannels = useMemo(() => channelsQuery.data?.items ?? [], [channelsQuery.data])

  const setSourceId = (id: number | null) => {
    setSourceIdState(id)
    if (id) localStorage.setItem('feedstudio.source', String(id))
    else localStorage.removeItem('feedstudio.source')
  }
  const setChannelId = (id: number | null) => {
    setChannelIdState(id)
    if (id) localStorage.setItem('feedstudio.channel', String(id))
    else localStorage.removeItem('feedstudio.channel')
  }

  // Fall back to the first available source / its first channel.
  useEffect(() => {
    if (sourcesQuery.isSuccess && (sourceId === null || !sources.some((s) => s.id === sourceId))) {
      setSourceId(sources[0]?.id ?? null)
    }
  }, [sourcesQuery.isSuccess, sources, sourceId])

  const channels = allChannels.filter((c) => c.source_id === sourceId)
  useEffect(() => {
    if (channelsQuery.isSuccess && channelId !== null && !channels.some((c) => c.id === channelId)) {
      setChannelId(channels[0]?.id ?? null)
    } else if (channelsQuery.isSuccess && channelId === null && channels.length > 0) {
      setChannelId(channels[0].id)
    }
  }, [channelsQuery.isSuccess, channels, channelId])

  const value: Workspace = {
    sources,
    channels,
    sourceId,
    channelId,
    source: sources.find((s) => s.id === sourceId) ?? null,
    channel: channels.find((c) => c.id === channelId) ?? null,
    setSourceId,
    setChannelId,
    loading: sourcesQuery.isLoading || channelsQuery.isLoading,
  }
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
}

export function useWorkspace(): Workspace {
  const ctx = useContext(WorkspaceContext)
  if (!ctx) throw new Error('useWorkspace must be used inside WorkspaceProvider')
  return ctx
}
