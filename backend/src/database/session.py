"""Database session management"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

# Get database URL from environment
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./heatmap.db')

# For SQLite, enable foreign keys
connect_args = {}
if DATABASE_URL.startswith('sqlite'):
    connect_args = {"check_same_thread": False}

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True  # Verify connections before using
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for database sessions"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database with default data"""
    from .models import Base, SystemConfig, DataSource
    import json

    # Create all tables
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Check if already initialized
        if db.query(SystemConfig).first():
            print("Database already initialized")
            return

        # Insert default system config
        default_configs = [
            SystemConfig(
                key='pricing_enabled',
                value='false',
                value_type='boolean',
                category='pricing',
                description='Enable/disable paid requests'
            ),
            SystemConfig(
                key='price_per_request',
                value='0.00',
                value_type='float',
                category='pricing',
                description='Price per analysis request in USD'
            ),
            SystemConfig(
                key='graph_depth_max',
                value='3',
                value_type='integer',
                category='analysis',
                description='Maximum graph traversal depth'
            ),
            SystemConfig(
                key='graph_depth_default',
                value='1',
                value_type='integer',
                category='analysis',
                description='Default graph traversal depth'
            ),
            SystemConfig(
                key='refresh_interval_days',
                value='7',
                value_type='integer',
                category='analysis',
                description='Data refresh interval in days'
            ),
            SystemConfig(
                key='email_notifications_enabled',
                value='true',
                value_type='boolean',
                category='notifications',
                description='Enable email notifications'
            ),
            SystemConfig(
                key='max_concurrent_jobs',
                value='5',
                value_type='integer',
                category='system',
                description='Max concurrent analysis jobs'
            ),
        ]

        for config in default_configs:
            db.add(config)

        # Insert default data sources
        default_sources = [
            DataSource(
                name='uniswap_v3',
                type='dex',
                enabled=True,
                api_endpoint='https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3',
                contract_addresses=['0x1F98431c8aD98523631AE4a59f267346ea31F984'],
                config={'fetch_method': 'subgraph'}
            ),
            DataSource(
                name='aave_v3',
                type='lending',
                enabled=False,  # Not yet implemented
                api_endpoint='https://api.thegraph.com/subgraphs/name/aave/protocol-v3',
                contract_addresses=['0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2'],
                config={'fetch_method': 'subgraph'}
            ),
        ]

        for source in default_sources:
            db.add(source)

        db.commit()
        print("✅ Database initialized with default data")

    except Exception as e:
        db.rollback()
        print(f"❌ Error initializing database: {e}")
        raise
    finally:
        db.close()
