import { VisualizationData, EmbeddingResponse, CommunityStat } from './types'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export class APIClient {
  private baseUrl: string

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl
  }

  private async fetch<T>(endpoint: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`)

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
      throw new Error(error.detail || `API Error: ${response.status}`)
    }

    return response.json()
  }

  async getVisualizationData(): Promise<VisualizationData> {
    return this.fetch<VisualizationData>('/api/visualization')
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
