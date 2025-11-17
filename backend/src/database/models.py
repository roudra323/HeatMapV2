"""Database models for production HeatMap"""
from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer,
    String, Text, DECIMAL, BigInteger, JSON, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class DataSource(Base):
    """Configurable data sources (Uniswap, Aave, etc.)"""
    __tablename__ = 'data_sources'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    type = Column(String(50), nullable=False)  # dex, lending, stablecoin, nft
    enabled = Column(Boolean, default=True)
    api_endpoint = Column(String(500))
    contract_addresses = Column(JSON)
    last_sync = Column(DateTime)
    config = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<DataSource(name='{self.name}', type='{self.type}', enabled={self.enabled})>"


class Wallet(Base):
    """Wallet addresses with analyzed behavior"""
    __tablename__ = 'wallets'

    address = Column(String(42), primary_key=True)
    first_seen = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_updated = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Activity metrics
    total_transactions = Column(Integer, default=0)
    unique_tokens = Column(Integer, default=0)
    unique_counterparties = Column(Integer, default=0)

    # Behavior ratios
    stablecoin_ratio = Column(Float, default=0.0)
    meme_ratio = Column(Float, default=0.0)
    defi_ratio = Column(Float, default=0.0)
    wrapped_ratio = Column(Float, default=0.0)
    nft_ratio = Column(Float, default=0.0)

    # Classification
    community = Column(String(50))

    # Embeddings
    pca_x = Column(Float)
    pca_y = Column(Float)
    tsne_x = Column(Float)
    tsne_y = Column(Float)

    # Status
    is_contract = Column(Boolean, default=False)
    analysis_status = Column(String(20), default='pending')  # pending, processing, completed, failed

    # Metadata
    metadata = Column(JSON)

    # Relationships
    sent_connections = relationship(
        'WalletConnection',
        foreign_keys='WalletConnection.from_address',
        back_populates='from_wallet'
    )
    received_connections = relationship(
        'WalletConnection',
        foreign_keys='WalletConnection.to_address',
        back_populates='to_wallet'
    )

    def __repr__(self):
        return f"<Wallet(address='{self.address}', community='{self.community}')>"

    def is_stale(self, days=7):
        """Check if wallet data needs refresh"""
        if not self.last_updated:
            return True
        delta = datetime.utcnow() - self.last_updated
        return delta.days >= days


class WalletConnection(Base):
    """Relationships between wallets (transaction graph)"""
    __tablename__ = 'wallet_connections'
    __table_args__ = (
        UniqueConstraint('from_address', 'to_address', name='_from_to_uc'),
    )

    id = Column(Integer, primary_key=True)
    from_address = Column(String(42), ForeignKey('wallets.address'), nullable=False)
    to_address = Column(String(42), ForeignKey('wallets.address'), nullable=False)

    transaction_count = Column(Integer, default=0)
    total_value = Column(DECIMAL(36, 18))
    first_interaction = Column(DateTime)
    last_interaction = Column(DateTime)

    # Relationships
    from_wallet = relationship('Wallet', foreign_keys=[from_address], back_populates='sent_connections')
    to_wallet = relationship('Wallet', foreign_keys=[to_address], back_populates='received_connections')

    def __repr__(self):
        return f"<WalletConnection(from='{self.from_address[:8]}...', to='{self.to_address[:8]}...', count={self.transaction_count})>"


class Transaction(Base):
    """Transaction cache for faster analysis"""
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True)
    tx_hash = Column(String(66), unique=True, nullable=False)

    from_address = Column(String(42))
    to_address = Column(String(42))
    value = Column(DECIMAL(36, 18))
    timestamp = Column(DateTime, nullable=False)

    # Token info
    token_address = Column(String(42))
    token_type = Column(String(20))  # ERC20, ERC721, ERC1155, ETH
    token_symbol = Column(String(20))

    # Source
    source = Column(String(50))  # uniswap, aave, etc.
    block_number = Column(BigInteger)

    def __repr__(self):
        return f"<Transaction(hash='{self.tx_hash[:10]}...', source='{self.source}')>"


class AnalysisRequest(Base):
    """User-initiated analysis requests"""
    __tablename__ = 'analysis_requests'

    id = Column(Integer, primary_key=True)
    request_id = Column(String(36), unique=True, nullable=False)

    wallet_address = Column(String(42), nullable=False)
    user_email = Column(String(255))

    # Parameters
    graph_depth = Column(Integer, default=1)
    priority = Column(Integer, default=5)

    # Status
    status = Column(String(20), default='queued')  # queued, processing, completed, failed

    # Pricing
    price_usd = Column(DECIMAL(10, 2), default=0.00)
    payment_status = Column(String(20), default='free')  # free, pending, paid, failed
    payment_id = Column(String(100))

    # Timestamps
    requested_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Results
    result_url = Column(String(500))
    error_message = Column(Text)

    # Metadata
    metadata = Column(JSON)

    def __repr__(self):
        return f"<AnalysisRequest(id='{self.request_id}', status='{self.status}')>"


class SystemConfig(Base):
    """System configuration key-value store"""
    __tablename__ = 'system_config'

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    value_type = Column(String(20), default='string')  # string, integer, float, boolean, json
    category = Column(String(50))
    description = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_typed_value(self):
        """Return value with correct type"""
        if self.value_type == 'integer':
            return int(self.value)
        elif self.value_type == 'float':
            return float(self.value)
        elif self.value_type == 'boolean':
            return self.value.lower() in ('true', '1', 'yes')
        elif self.value_type == 'json':
            import json
            return json.loads(self.value)
        return self.value

    def __repr__(self):
        return f"<SystemConfig(key='{self.key}', value='{self.value}')>"
