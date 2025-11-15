# HeatMap V2: Wallet Behavior Analytics Platform

An interactive blockchain wallet behavior analysis platform powered by machine learning, designed for Web3 marketers to identify wallet patterns, communities, and connections.

## Features

### Advanced ML Analysis
- **t-SNE & PCA Visualization**: Dimensionality reduction for exploring wallet behavior clusters
- **Behavior-Based Communities**: Automatic classification into 9 distinct communities:
  - NFT Trader (127 wallets)
  - Stablecoin User (65 wallets)
  - Meme Trader (2 wallets)
  - DeFi User (1 wallet)
  - Receiver/Collector (195 wallets)
  - Sender/Distributor (58 wallets)
  - High Activity Hub (14 wallets)
  - Mixed Behavior (46 wallets)
  - Wrapper/Bridge User (3 wallets)

### Interactive Visualizations
- **Scatter Plot**: PCA/t-SNE embeddings with community color coding
- **Network Graph**: Wallet-to-wallet interaction network with force-directed layout
- **Community Statistics**: Detailed breakdown of each behavior community
- **Interactive Filters**: Filter by community, toggle visualization methods

### Data Coverage
- **511 analyzed wallets** from minimal dataset
- **21,181 total transfers** (ERC20, ERC721, ERC1155)
- **10,214 network nodes** with 12,363 connections
- **9 behavior communities** detected

## Quick Start

### Prerequisites
- Python 3.9+
- Node.js 18+
- pip and npm

### Backend Setup

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Run ML analysis on minimal data
python visualize.py

# Start API server
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Backend will be available at http://localhost:8000

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

Frontend will be available at http://localhost:3000

## API Endpoints

### Visualization Endpoints
- `GET /api/visualization` - Complete visualization data (wallets, embeddings, network, stats)
- `GET /api/communities` - Behavior community statistics
- `GET /api/embeddings?method=tsne&community=NFT+Trader` - Filtered embeddings
- `GET /api/wallets` - Paginated wallet list
- `GET /api/stats` - Overall statistics
- `GET /health` - Health check

## Behavior Community Detection

### Classification Logic

- **NFT Trader**: Wallets with ERC721/ERC1155 transactions
- **Stablecoin User**: >50% stablecoin (USDT, USDC, DAI) transactions
- **Meme Trader**: >50% meme coin (PEPE, SHIB, etc.) transactions
- **DeFi User**: >50% DeFi protocol (UNI, AAVE, etc.) transactions
- **Wrapper/Bridge User**: >50% wrapped asset (WETH, WBTC) transactions
- **High Activity Hub**: >20 unique counterparties
- **Sender/Distributor**: >80% outgoing transactions
- **Receiver/Collector**: >80% incoming transactions
- **Mixed Behavior**: No dominant pattern

## Use Cases for Web3 Marketers

### 1. Audience Segmentation
Identify and target specific wallet behaviors:
- NFT collectors for NFT project launches
- Stablecoin users for trading platforms
- DeFi users for protocol integrations

### 2. Wallet Clustering
Discover similar wallet patterns using t-SNE visualization:
- Nearby wallets in embedding space have similar behaviors
- Filter by community to focus on specific segments

### 3. Network Analysis
Find connected wallets:
- Identify wallet clusters that transact together
- Discover influential hubs with high connectivity
- Map token distribution networks

## Technology Stack

### Backend
- FastAPI, Pandas, Scikit-learn (t-SNE, PCA, KMeans)
- NetworkX for graph analysis
- Web3.py, Etherscan API, The Graph

### Frontend
- Next.js 14 + TypeScript
- Recharts for scatter plots
- Canvas API for network graphs
- Tailwind CSS

## License

MIT
