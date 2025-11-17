"""Data source configuration"""
import yaml
from pathlib import Path
from typing import Dict, List, Any
from dataclasses import dataclass


@dataclass
class SourceConfig:
    """Data source configuration"""
    name: str
    type: str
    enabled: bool
    api_endpoint: str = None
    contracts: List[str] = None
    fetch_method: str = 'subgraph'
    config: Dict[str, Any] = None

    def __post_init__(self):
        if self.contracts is None:
            self.contracts = []
        if self.config is None:
            self.config = {}


def load_source_config(config_file: str = None) -> Dict[str, SourceConfig]:
    """Load data sources from YAML config"""
    if config_file is None:
        config_file = Path(__file__).parent.parent.parent / 'config' / 'sources.yaml'

    # Create default config if doesn't exist
    if not Path(config_file).exists():
        default_config = {
            'data_sources': {
                'uniswap_v3': {
                    'enabled': True,
                    'type': 'dex',
                    'api_endpoint': 'https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3',
                    'contracts': ['0x1F98431c8aD98523631AE4a59f267346ea31F984'],
                    'fetch_method': 'subgraph'
                },
                'aave_v3': {
                    'enabled': False,
                    'type': 'lending',
                    'api_endpoint': 'https://api.thegraph.com/subgraphs/name/aave/protocol-v3',
                    'contracts': ['0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2'],
                    'fetch_method': 'subgraph'
                }
            },
            'token_categories': {
                'stablecoins': ['USDT', 'USDC', 'DAI', 'BUSD', 'FRAX'],
                'defi': ['UNI', 'AAVE', 'COMP', 'CRV', 'SNX'],
                'meme': ['PEPE', 'SHIB', 'DOGE', 'FLOKI']
            },
            'analysis': {
                'graph_depth_max': 3,
                'graph_depth_default': 1,
                'min_transactions': 5,
                'refresh_interval_days': 7
            }
        }

        Path(config_file).parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False)

    # Load config
    with open(config_file, 'r') as f:
        config_data = yaml.safe_load(f)

    # Parse sources
    sources = {}
    for name, data in config_data.get('data_sources', {}).items():
        sources[name] = SourceConfig(
            name=name,
            type=data.get('type', 'unknown'),
            enabled=data.get('enabled', False),
            api_endpoint=data.get('api_endpoint'),
            contracts=data.get('contracts', []),
            fetch_method=data.get('fetch_method', 'subgraph'),
            config=data.get('config', {})
        )

    return sources


def get_enabled_sources() -> List[SourceConfig]:
    """Get list of enabled data sources"""
    all_sources = load_source_config()
    return [source for source in all_sources.values() if source.enabled]
