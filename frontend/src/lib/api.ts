import { VisualizationData, EmbeddingResponse, CommunityStat } from './types'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const DATA_SOURCE = process.env.NEXT_PUBLIC_DATA_SOURCE || 'backend' // 'local' or 'backend'

export class APIClient {
  private baseUrl: string
  private dataSource: 'local' | 'backend'

  constructor(baseUrl: string = API_BASE, dataSource: 'local' | 'backend' = DATA_SOURCE as 'local' | 'backend') {
    this.baseUrl = baseUrl
    this.dataSource = dataSource
  }

  private async fetch<T>(endpoint: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`)

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
      throw new Error(error.detail || `API Error: ${response.status}`)
    }

    return response.json()
  }

  private async fetchLocal<T>(path: string): Promise<T> {
    const response = await fetch(path)

    if (!response.ok) {
      throw new Error(`Failed to load local data: ${response.status}`)
    }

    return response.json()
  }

  async getVisualizationData(): Promise<VisualizationData> {
    if (this.dataSource === 'local') {
      // Load from public/data folder
      return this.fetchLocal<VisualizationData>('/data/visualization_data.json')
    } else {
      // Fetch from backend API
      return this.fetch<VisualizationData>('/api/visualization')
    }
  }

  async getCommunities(): Promise<{ communities: CommunityStat[]; total: number }> {
    return this.fetch<{ communities: CommunityStat[]; total: number }>('/api/communities')
  }

  async getEmbeddings(method: 'pca' | 'tsne', community?: string): Promise<EmbeddingResponse> {
    const params = new URLSearchParams({ method })
    if (community) params.append('community', community)

    return this.fetch<EmbeddingResponse>(`/api/embeddings?${params}`)
  }

  async getHealth(): Promise<{ status: string }> {
    return this.fetch<{ status: string }>('/health')
  }
}

export const apiClient = new APIClient()
