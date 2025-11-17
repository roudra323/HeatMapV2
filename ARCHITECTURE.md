# HeatMap V2 - Production Architecture Design

## System Overview

Transform HeatMap from static analysis tool to production-grade, on-demand wallet intelligence platform.

## Core Features

### 1. Configurable Multi-Source Data Collection
- **Data Sources** (configurable):
  - Uniswap (current)
  - Aave
  - Compound
  - Curve
  - PerpDEXs (dYdX, GMX, etc.)
  - Stablecoin contracts (USDC, USDT, DAI)
  - NFT marketplaces (OpenSea, Blur)
  - More sources added via config

### 2. Automated Data Refresh
- Scheduled job runs every 7 days
- Updates all tracked wallet data
- Incremental updates (fetch new data since last run)

### 3. On-Demand Address Analysis
**User Flow:**
1. User requests wallet address analysis
2. System checks if address exists in DB:
   - If exists & fresh (< 7 days): Return immediately
   - If exists & stale: Queue refresh job
   - If new: Queue full analysis job
3. User receives: "Analysis queued. We'll email you when ready."
4. Background job processes request
5. Email sent when complete with link to results

**Analysis Process:**
1. Fetch all transactions for target address
2. Extract wallet addresses (filter contracts)
3. Fetch connected wallets up to N levels (configurable)
4. For each wallet:
   - Get ERC20/721/1155 transfers
   - Classify tokens (DeFi, meme, stablecoin, NFT)
   - Calculate behavior metrics
5. Run ML analysis (t-SNE, PCA, communities)
6. Store results in database
7. Send notification

### 4. Pricing System
- Backend-configurable pricing
- Toggle: FREE or PAID
- When FREE: unlimited requests
- When PAID: charge per request
- Admin can set price per address analysis
- Payment methods: Stripe, crypto (future)

## Architecture Components

### Database Layer (PostgreSQL)

**Tables:**

```sql
-- Data sources configuration
CREATE TABLE data_sources (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    type VARCHAR(50) NOT NULL,  -- 'dex', 'lending', 'stablecoin', 'nft', etc.
    enabled BOOLEAN DEFAULT TRUE,
    api_endpoint VARCHAR(500),
    contract_addresses JSONB,
    last_sync TIMESTAMP,
    config JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Wallets database
CREATE TABLE wallets (
    address VARCHAR(42) PRIMARY KEY,
    first_seen TIMESTAMP NOT NULL,
    last_updated TIMESTAMP NOT NULL,
    total_transactions INTEGER DEFAULT 0,
    unique_tokens INTEGER DEFAULT 0,
    unique_counterparties INTEGER DEFAULT 0,

    -- Behavior ratios
    stablecoin_ratio FLOAT DEFAULT 0,
    meme_ratio FLOAT DEFAULT 0,
    defi_ratio FLOAT DEFAULT 0,
    wrapped_ratio FLOAT DEFAULT 0,
    nft_ratio FLOAT DEFAULT 0,

    -- Community classification
    community VARCHAR(50),

    -- Embeddings
    pca_x FLOAT,
    pca_y FLOAT,
    tsne_x FLOAT,
    tsne_y FLOAT,

    -- Metadata
    is_contract BOOLEAN DEFAULT FALSE,
    analysis_status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, completed, failed
    metadata JSONB
);

-- Wallet relationships (graph)
CREATE TABLE wallet_connections (
    id SERIAL PRIMARY KEY,
    from_address VARCHAR(42) REFERENCES wallets(address),
    to_address VARCHAR(42) REFERENCES wallets(address),
    transaction_count INTEGER DEFAULT 0,
    total_value NUMERIC(36, 18),
    first_interaction TIMESTAMP,
    last_interaction TIMESTAMP,
    UNIQUE(from_address, to_address)
);

-- Transactions cache
CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    tx_hash VARCHAR(66) UNIQUE NOT NULL,
    from_address VARCHAR(42),
    to_address VARCHAR(42),
    value NUMERIC(36, 18),
    timestamp TIMESTAMP NOT NULL,
    token_address VARCHAR(42),
    token_type VARCHAR(20),  -- ERC20, ERC721, ERC1155, ETH
    token_symbol VARCHAR(20),
    source VARCHAR(50),  -- uniswap, aave, etc.
    block_number BIGINT
);

-- Analysis requests (user-initiated)
CREATE TABLE analysis_requests (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(36) UNIQUE NOT NULL,
    wallet_address VARCHAR(42) NOT NULL,
    user_email VARCHAR(255),
    status VARCHAR(20) DEFAULT 'queued',  -- queued, processing, completed, failed
    graph_depth INTEGER DEFAULT 1,
    priority INTEGER DEFAULT 5,

    -- Pricing
    price_usd NUMERIC(10, 2) DEFAULT 0,
    payment_status VARCHAR(20) DEFAULT 'free',  -- free, pending, paid, failed
    payment_id VARCHAR(100),

    -- Timestamps
    requested_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Results
    result_url VARCHAR(500),
    error_message TEXT,

    -- Metadata
    metadata JSONB
);

-- System configuration
CREATE TABLE system_config (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    value_type VARCHAR(20) DEFAULT 'string',  -- string, integer, float, boolean, json
    category VARCHAR(50),
    description TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Insert default config
INSERT INTO system_config (key, value, value_type, category, description) VALUES
('pricing_enabled', 'false', 'boolean', 'pricing', 'Enable/disable paid requests'),
('price_per_request', '0.00', 'float', 'pricing', 'Price per analysis request in USD'),
('graph_depth_max', '3', 'integer', 'analysis', 'Maximum graph traversal depth'),
('graph_depth_default', '1', 'integer', 'analysis', 'Default graph traversal depth'),
('refresh_interval_days', '7', 'integer', 'analysis', 'Data refresh interval in days'),
('email_notifications_enabled', 'true', 'boolean', 'notifications', 'Enable email notifications'),
('max_concurrent_jobs', '5', 'integer', 'system', 'Max concurrent analysis jobs');
```

### Background Job System (Celery + Redis)

**Architecture:**
- **Celery**: Distributed task queue
- **Redis**: Message broker + result backend
- **Workers**: Process analysis jobs

**Job Types:**
1. `analyze_wallet_task` - Full wallet analysis
2. `refresh_wallet_task` - Update existing wallet
3. `scheduled_refresh_task` - Weekly batch refresh
4. `graph_traversal_task` - Multi-level connection analysis

### Configuration System

**File: `backend/config/sources.yaml`**
```yaml
# Data sources configuration
data_sources:
  uniswap_v3:
    enabled: true
    type: dex
    subgraph_url: https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3
    contracts:
      - 0x1F98431c8aD98523631AE4a59f267346ea31F984  # Factory
    fetch_method: subgraph

  aave_v3:
    enabled: true
    type: lending
    subgraph_url: https://api.thegraph.com/subgraphs/name/aave/protocol-v3
    contracts:
      - 0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2  # Pool
    fetch_method: subgraph

  curve:
    enabled: true
    type: dex
    subgraph_url: https://api.thegraph.com/subgraphs/name/curve-fi/curve
    fetch_method: subgraph

  gmx:
    enabled: true
    type: perpdex
    api_url: https://api.gmx.io
    fetch_method: api

  usdc_contract:
    enabled: true
    type: stablecoin
    contracts:
      - 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48  # USDC
    fetch_method: etherscan

  opensea:
    enabled: false  # Coming soon
    type: nft_marketplace
    api_url: https://api.opensea.io/api/v2

# Token classification
token_categories:
  stablecoins:
    - USDT
    - USDC
    - DAI
    - BUSD
    - FRAX

  defi:
    - UNI
    - AAVE
    - COMP
    - CRV
    - SNX

  meme:
    - PEPE
    - SHIB
    - DOGE
    - FLOKI

# Analysis parameters
analysis:
  graph_depth_max: 3
  graph_depth_default: 1
  min_transactions: 5
  refresh_interval_days: 7
  batch_size: 100

# Pricing
pricing:
  enabled: false
  price_per_request_usd: 0.00
  free_tier_requests_per_day: 10
  stripe_enabled: false
  crypto_payment_enabled: false
```

### API Endpoints (New/Updated)

```python
# Request on-demand analysis
POST /api/v2/analysis/request
Body: {
  "wallet_address": "0x...",
  "email": "user@example.com",
  "graph_depth": 2  # optional
}
Response: {
  "request_id": "uuid",
  "status": "queued",
  "message": "Analysis queued. You'll receive an email when ready.",
  "estimated_time_minutes": 10,
  "price_usd": 0.00
}

# Check analysis status
GET /api/v2/analysis/status/{request_id}
Response: {
  "request_id": "uuid",
  "status": "processing",
  "progress": 45,
  "wallet_address": "0x...",
  "started_at": "2025-11-15T10:00:00Z"
}

# Get analysis results
GET /api/v2/analysis/results/{request_id}
Response: {
  "request_id": "uuid",
  "wallet_address": "0x...",
  "status": "completed",
  "wallet_data": {...},
  "connected_wallets": [...],
  "communities": [...],
  "completed_at": "2025-11-15T10:15:00Z"
}

# Admin: Get/Update system config
GET /api/v2/admin/config
POST /api/v2/admin/config
Body: {
  "pricing_enabled": true,
  "price_per_request": 5.00
}

# Admin: Manage data sources
GET /api/v2/admin/sources
POST /api/v2/admin/sources/{source_name}/toggle
```

## Implementation Phases

### Phase 1: Foundation (Week 1)
- [ ] PostgreSQL database setup
- [ ] Database models and migrations
- [ ] Configuration system
- [ ] Basic API endpoints

### Phase 2: Background Jobs (Week 2)
- [ ] Celery + Redis setup
- [ ] Basic job tasks
- [ ] Job status tracking
- [ ] Email notifications

### Phase 3: Multi-Source Collectors (Week 3)
- [ ] Refactor collectors for multi-source
- [ ] Implement Aave collector
- [ ] Implement Curve collector
- [ ] Implement stablecoin tracking
- [ ] Contract filtering

### Phase 4: Graph Traversal (Week 4)
- [ ] Recursive wallet fetching
- [ ] Level-based traversal
- [ ] Connection tracking
- [ ] Deduplication

### Phase 5: Pricing & Payments (Week 5)
- [ ] Pricing configuration
- [ ] Stripe integration (optional)
- [ ] Request validation
- [ ] Admin dashboard

### Phase 6: Scheduled Jobs (Week 6)
- [ ] Weekly refresh scheduler
- [ ] Incremental updates
- [ ] Batch processing
- [ ] Error handling

### Phase 7: Frontend Updates (Week 7)
- [ ] Request analysis form
- [ ] Status tracking page
- [ ] Payment integration (if enabled)
- [ ] Admin panel

## Technology Stack Updates

**New Dependencies:**
- `celery` - Distributed task queue
- `redis` - Message broker
- `psycopg2` - PostgreSQL driver
- `sqlalchemy` - ORM
- `alembic` - Database migrations
- `stripe` - Payment processing
- `sendgrid` - Email service
- `aiohttp` - Async HTTP requests
- `celery-beat` - Scheduled tasks

## Deployment Considerations

**Infrastructure:**
- PostgreSQL database (RDS, Supabase, or self-hosted)
- Redis instance (ElastiCache or self-hosted)
- Celery workers (multiple instances for scalability)
- Backend API (Docker container, EC2, or serverless)
- Frontend (Vercel, Netlify, or CloudFront)

**Environment Variables:**
```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/heatmap

# Redis
REDIS_URL=redis://localhost:6379/0

# APIs
QUICKNODE_API_KEY=xxx
ETHERSCAN_API_KEY=xxx
THE_GRAPH_API_KEY=xxx

# Email
SENDGRID_API_KEY=xxx
NOTIFICATION_EMAIL_FROM=noreply@heatmap.io

# Payments (optional)
STRIPE_SECRET_KEY=xxx
STRIPE_WEBHOOK_SECRET=xxx

# Config
PRICING_ENABLED=false
PRICE_PER_REQUEST=0.00
```

## Monitoring & Logging

- **Job monitoring**: Flower (Celery monitoring tool)
- **Application logs**: Structured logging with timestamps
- **Metrics**: Track job completion times, success rates
- **Alerts**: Failed jobs, high queue depth, API errors

## Security Considerations

- Rate limiting on API endpoints
- Email verification for analysis requests
- Payment verification before processing
- API key rotation
- Encrypted sensitive config
- Contract address validation

## Cost Estimation (AWS Example)

**Monthly costs (estimated):**
- RDS PostgreSQL (t3.micro): $15-20
- Redis (t3.micro): $12-15
- EC2 for Celery workers (t3.small x2): $30-40
- API hosting (EC2 t3.micro): $8-10
- Data transfer: $10-20
- **Total**: $75-105/month (low traffic)

**Scaling costs:**
- Add workers as request volume increases
- Upgrade database for more connections
- Consider serverless for API (Lambda + API Gateway)

## Next Steps

1. Review and approve architecture
2. Set up development environment
3. Begin Phase 1 implementation
4. Create detailed task breakdown for each phase
