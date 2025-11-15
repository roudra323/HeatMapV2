# HeatMap Backend

Backend API and data processing system for blockchain wallet behavior analysis and ML insights.

## Overview

HeatMap Backend is a FastAPI-based service that collects blockchain data from multiple sources (Uniswap, Etherscan, QuickNode) and performs machine learning analysis to identify wallet patterns, detect anomalies, and build network graphs of wallet interactions.

## Features

- 🔍 **Data Collection**: Fetch trading data from Uniswap v3, transfer data from Etherscan, and validate wallet addresses via QuickNode
- 🤖 **Machine Learning**: Clustering, anomaly detection, and network analysis
- 📊 **REST API**: FastAPI endpoints for wallets, clusters, anomalies, and network data
- 🛠️ **CLI Tools**: Command-line interfaces for data collection and analysis
- 📈 **Network Analysis**: Build and analyze wallet interaction graphs

## Architecture

```
backend/
├── api.py              # FastAPI application entry point
├── collector.py        # CLI for data collection
├── analyzer.py         # CLI for ML analysis
├── config/             # Configuration files
├── src/
│   ├── api/           # API routes and models
│   ├── collectors/    # Data collection modules
│   └── ml/            # Machine learning modules
└── data/              # Data storage
    ├── raw/           # Raw collected data
    ├── processed/     # Processed data
    └── results/       # Analysis results
```

## Installation

### Prerequisites

- Python 3.9+
- pip

### Setup

1. **Clone the repository** (if not already done):
```bash
cd backend
```

2. **Create a virtual environment**:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Create `.env` file**:
```bash
cp .env.example .env  # Or create manually
```

5. **Configure environment variables** (see [Configuration](#configuration) section)

## Configuration

### Environment Variables

Create a `.env` file in the `backend/` directory with the following variables:

```env
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000

# Etherscan API
ETHERSCAN_API_KEY=your_etherscan_api_key

# QuickNode RPC Endpoint
QUICKNODE_API_KEY=https://your-quicknode-endpoint.com

# Optional: Database (if using in future)
DATABASE_URL=sqlite:///data/heatmap.db
```

### Config File

Edit `config/base.yaml` to customize:
- API settings (CORS origins, version)
- Collector settings (rate limits, timeouts)
- Analyzer settings (cluster count, network depth)

## Usage

### Running the API Server

```bash
python api.py
```

Or using uvicorn directly:
```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at:
- **API**: http://localhost:8000
- **Docs**: http://localhost:8000/docs (Swagger UI)
- **ReDoc**: http://localhost:8000/redoc
- **Health**: http://localhost:8000/health

### Data Collection

#### Collect Uniswap Trades

```bash
python collector.py --uniswap --limit 1000
```

This will:
- Fetch recent Uniswap v3 swaps
- Extract unique wallet addresses
- Save to `data/raw/uniswap_trades.csv` and `data/raw/uniswap_wallets.csv`

#### Collect Transfer Data

```bash
python collector.py --transfers 0x1234567890abcdef1234567890abcdef12345678
```

Fetches ERC20 and ERC721 transfers for a specific wallet address.

#### Validate Wallet Addresses

```bash
python collector.py --validate wallets.txt
```

Validates addresses from a file (one per line) and checks if they're wallets or contracts.

### Data Analysis

#### Run Clustering Analysis

```bash
python analyzer.py --input data/processed/wallets.csv --clustering --n-clusters 5
```

#### Detect Anomalies

```bash
python analyzer.py --input data/processed/wallets.csv --anomaly
```

#### Network Analysis

```bash
python analyzer.py --input data/processed/transfers.csv --network
```

#### Run All Analyses

```bash
python analyzer.py --input data/processed/wallets.csv --all
```

## API Endpoints

### Wallets

- `GET /api/wallets` - Get paginated list of wallets
  - Query params: `limit` (default: 100), `skip` (default: 0)
- `GET /api/wallets/{address}` - Get specific wallet details

### Analysis

- `GET /api/clusters` - Get clustering analysis results
- `GET /api/anomalies` - Get anomaly detection results
- `GET /api/network` - Get network graph data (nodes, edges, stats)

### Statistics

- `GET /api/stats` - Get overall statistics (total wallets, clusters, anomalies, transactions)

### Health

- `GET /health` - Health check endpoint

## Data Collectors

### UniswapCollector

Fetches trading data from Uniswap v3 using The Graph subgraph.

**Methods**:
- `fetch_trades(limit, skip)` - Fetch recent swaps
- `get_unique_wallets(trades_df)` - Extract unique wallet addresses

### EtherscanCollector

Fetches transfer data from Etherscan API.

**Methods**:
- `fetch_erc20_transfers(address)` - Fetch ERC20 token transfers
- `fetch_erc721_transfers(address)` - Fetch ERC721 (NFT) transfers
- `fetch_all_transfers(address)` - Fetch all transfer types

### QuickNodeCollector

Validates addresses using QuickNode RPC endpoint.

**Methods**:
- `is_contract(address)` - Check if address is a contract
- `validate_wallets(addresses)` - Validate a list of addresses

## Machine Learning Modules

### WalletClusterer

Clusters wallets based on behavior patterns using K-Means.

**Features**: transaction_count, total_volume, avg_transaction_value, unique_tokens

### AnomalyDetector

Detects anomalous wallet behavior using Isolation Forest.

**Features**: transaction_count, total_volume, avg_transaction_value, unique_tokens, unique_counterparties

### NetworkAnalyzer

Builds and analyzes wallet interaction networks using NetworkX.

**Capabilities**:
- Build graph from transfer data
- Calculate network metrics (degree, clustering coefficient)
- Detect communities
- Export for visualization

## Project Structure

```
backend/
├── api.py                 # FastAPI app entry point
├── collector.py           # Data collection CLI
├── analyzer.py            # Analysis CLI
├── requirements.txt       # Python dependencies
├── config/
│   └── base.yaml         # Configuration file
├── src/
│   ├── api/
│   │   ├── routes.py     # API route handlers
│   │   └── models.py     # Pydantic models
│   ├── collectors/
│   │   ├── uniswap.py    # Uniswap data collector
│   │   ├── etherscan.py  # Etherscan data collector
│   │   └── quicknode.py  # QuickNode validator
│   └── ml/
│       ├── clustering.py # Wallet clustering
│       ├── anomaly.py    # Anomaly detection
│       └── network.py    # Network analysis
└── data/
    ├── raw/              # Raw collected data
    ├── processed/        # Processed data
    └── results/          # Analysis results
```

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black .
```

### Type Checking

```bash
mypy src/
```

## Dependencies

Key dependencies:
- **FastAPI**: Web framework for building APIs
- **pandas**: Data manipulation and analysis
- **scikit-learn**: Machine learning algorithms
- **networkx**: Network analysis
- **subgrounds**: The Graph subgraph queries
- **web3**: Ethereum interaction
- **requests**: HTTP requests

See `requirements.txt` for complete list.

## Data Flow

1. **Collection**: Use `collector.py` to fetch data from blockchain sources
2. **Processing**: Raw data is stored in `data/raw/`
3. **Analysis**: Use `analyzer.py` to run ML analysis on processed data
4. **Results**: Analysis results stored in `data/results/`
5. **API**: FastAPI serves processed data and results to frontend

## Troubleshooting

### API Key Issues

- Ensure `.env` file exists and contains valid API keys
- Check API key permissions and rate limits

### Data Not Found Errors

- Run data collection first: `python collector.py --uniswap`
- Ensure data files exist in `data/processed/` or `data/results/`

### Import Errors

- Activate virtual environment: `source venv/bin/activate`
- Reinstall dependencies: `pip install -r requirements.txt`

## License

See main project LICENSE file.

## Contributing

1. Create a feature branch
2. Make your changes
3. Add tests if applicable
4. Submit a pull request

