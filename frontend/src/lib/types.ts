export interface Wallet {
  address: string
  total_transactions: number
  unique_tokens: number
  unique_counterparties: number
  stablecoin_ratio: number
  meme_ratio: number
  defi_ratio: number
  wrapped_ratio: number
  nft_ratio: number
  community: string
  communities?: string[] // All communities the wallet qualifies for
  pca_x: number
  pca_y: number
  tsne_x: number
  tsne_y: number
}

export interface CommunityStat {
  community: string
  total_txs: number
  wallet_count: number
  avg_stablecoin_ratio: number
  avg_meme_ratio: number
  avg_defi_ratio: number
  avg_nft_ratio: number
}

export interface NetworkNode {
  id: string
  community: string
  transactions: number
}

export interface NetworkEdge {
  source: string
  target: string
  weight: number
}

export interface NetworkData {
  nodes: NetworkNode[]
  edges: NetworkEdge[]
}

export interface VisualizationData {
  wallets: Wallet[]
  network: NetworkData | null
  community_stats: CommunityStat[]
  summary: {
    total_wallets: number
    total_communities: number
    pca_explained_variance: number
  }
}

export interface Embedding {
  address: string
  x: number
  y: number
  community: string
  total_transactions: number
}

export interface EmbeddingResponse {
  method: 'pca' | 'tsne'
  community_filter: string | null
  total: number
  embeddings: Embedding[]
}
