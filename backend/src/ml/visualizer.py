"""Advanced Wallet Visualization with t-SNE, PCA, and Behavior-Based Communities"""
import pandas as pd
import numpy as np
from sklearn.manifold import TSNE
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import networkx as nx
from typing import Dict, List, Tuple
import re


class WalletBehaviorAnalyzer:
    """Analyze wallet behavior patterns and create interactive visualizations"""

    # Token categorization patterns
    STABLECOINS = ['USDT', 'USDC', 'DAI', 'BUSD', 'FRAX', 'TUSD', 'USDP', 'GUSD']
    WRAPPED_ASSETS = ['WETH', 'WBTC', 'WMATIC', 'WBNB']
    MEME_COINS = ['PEPE', 'SHIB', 'DOGE', 'FLOKI', 'BONK', 'WIF', 'DOGE', 'ELON', 'BABYDOGE']
    DEFI_TOKENS = ['UNI', 'AAVE', 'COMP', 'SNX', 'CRV', 'MKR', 'SUSHI', 'BAL', '1INCH', 'YFI']

    def __init__(self, random_state: int = 42):
        self.random_state = random_state
        self.scaler = StandardScaler()
        self.pca = PCA(n_components=2, random_state=random_state)
        self.tsne = TSNE(n_components=2, random_state=random_state, perplexity=30, max_iter=1000)
        self.wallets_df = None
        self.features_df = None
        self.embeddings = {}

    def categorize_token(self, symbol: str) -> str:
        """Categorize token by type"""
        if not symbol or pd.isna(symbol):
            return 'unknown'

        symbol = symbol.upper()

        if symbol in self.STABLECOINS:
            return 'stablecoin'
        elif symbol in self.WRAPPED_ASSETS:
            return 'wrapped'
        elif symbol in self.MEME_COINS or any(meme in symbol for meme in ['MOON', 'SAFE', 'INU']):
            return 'meme'
        elif symbol in self.DEFI_TOKENS:
            return 'defi'
        else:
            return 'other'

    def extract_wallet_features(self, wallet_address: str, transfers_df: pd.DataFrame) -> Dict:
        """Extract comprehensive features for a single wallet"""

        # Filter transfers for this wallet
        wallet_transfers = transfers_df[
            (transfers_df['from'] == wallet_address) |
            (transfers_df['to'] == wallet_address)
        ].copy()

        if len(wallet_transfers) == 0:
            return None

        # Categorize each token
        wallet_transfers['token_category'] = wallet_transfers['tokenSymbol'].apply(self.categorize_token)

        # Basic metrics
        total_txs = len(wallet_transfers)
        unique_tokens = wallet_transfers['tokenSymbol'].nunique()
        unique_counterparties = pd.concat([
            wallet_transfers['from'],
            wallet_transfers['to']
        ]).nunique() - 1  # Exclude the wallet itself

        # Sent vs received
        sent_txs = len(wallet_transfers[wallet_transfers['from'] == wallet_address])
        received_txs = len(wallet_transfers[wallet_transfers['to'] == wallet_address])

        # Category-based features
        category_counts = wallet_transfers['token_category'].value_counts()

        stablecoin_txs = category_counts.get('stablecoin', 0)
        meme_txs = category_counts.get('meme', 0)
        defi_txs = category_counts.get('defi', 0)
        wrapped_txs = category_counts.get('wrapped', 0)
        nft_txs = 0  # Will be calculated from ERC721 data

        # Calculate ratios
        total_categorized = stablecoin_txs + meme_txs + defi_txs + wrapped_txs

        features = {
            'address': wallet_address,
            'total_transactions': total_txs,
            'unique_tokens': unique_tokens,
            'unique_counterparties': unique_counterparties,
            'sent_ratio': sent_txs / total_txs if total_txs > 0 else 0,
            'received_ratio': received_txs / total_txs if total_txs > 0 else 0,

            # Category counts
            'stablecoin_txs': stablecoin_txs,
            'meme_txs': meme_txs,
            'defi_txs': defi_txs,
            'wrapped_txs': wrapped_txs,
            'nft_txs': nft_txs,
            'other_txs': category_counts.get('other', 0),

            # Category ratios
            'stablecoin_ratio': stablecoin_txs / total_txs if total_txs > 0 else 0,
            'meme_ratio': meme_txs / total_txs if total_txs > 0 else 0,
            'defi_ratio': defi_txs / total_txs if total_txs > 0 else 0,
            'wrapped_ratio': wrapped_txs / total_txs if total_txs > 0 else 0,

            # Temporal features
            'first_tx_timestamp': wallet_transfers['timeStamp'].min(),
            'last_tx_timestamp': wallet_transfers['timeStamp'].max(),
            'activity_span_days': (wallet_transfers['timeStamp'].max() - wallet_transfers['timeStamp'].min()) / 86400,
        }

        return features

    def assign_behavior_community(self, features: pd.Series) -> str:
        """Assign wallet to behavior-based community"""

        # Define thresholds
        HIGH_THRESHOLD = 0.5
        MEDIUM_THRESHOLD = 0.3

        # Check dominant behavior
        if features['nft_txs'] > 0 and features['total_transactions'] > 5:
            return 'NFT Trader'
        elif features['stablecoin_ratio'] > HIGH_THRESHOLD:
            return 'Stablecoin User'
        elif features['meme_ratio'] > HIGH_THRESHOLD:
            return 'Meme Trader'
        elif features['defi_ratio'] > HIGH_THRESHOLD:
            return 'DeFi User'
        elif features['wrapped_ratio'] > HIGH_THRESHOLD:
            return 'Wrapper/Bridge User'
        elif features['meme_ratio'] > MEDIUM_THRESHOLD and features['defi_ratio'] > MEDIUM_THRESHOLD:
            return 'Active Trader'
        elif features['unique_counterparties'] > 20:
            return 'High Activity Hub'
        elif features['sent_ratio'] > 0.8:
            return 'Sender/Distributor'
        elif features['received_ratio'] > 0.8:
            return 'Receiver/Collector'
        else:
            return 'Mixed Behavior'

    def load_and_process_minimal_data(self, data_dir: str = None) -> pd.DataFrame:
        """Load all minimal data and extract wallet features"""
        import os
        import glob
        
        # Determine data directory path dynamically if not provided
        if data_dir is None:
            # Get the backend directory (parent of src directory)
            current_file = os.path.abspath(__file__)
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
            data_dir = os.path.join(backend_dir, 'minimal_data')
        
        print(f"Loading minimal data from: {data_dir}")

        # Load all ERC20 transfers
        erc20_files = glob.glob(f'{data_dir}/erc20_minimal/*.csv')
        erc721_files = glob.glob(f'{data_dir}/erc721_minimal/*.csv')
        erc1155_files = glob.glob(f'{data_dir}/erc1155_minimal/*.csv')

        all_transfers = []

        # Load ERC20 data
        print(f"Loading {len(erc20_files)} ERC20 files...")
        for file in erc20_files:
            try:
                df = pd.read_csv(file)
                if len(df) > 0:
                    df['token_type'] = 'ERC20'
                    all_transfers.append(df)
            except Exception as e:
                print(f"Error loading {file}: {e}")

        # Load ERC721 data
        print(f"Loading {len(erc721_files)} ERC721 files...")
        for file in erc721_files:
            try:
                df = pd.read_csv(file)
                if len(df) > 0:
                    df['token_type'] = 'ERC721'
                    all_transfers.append(df)
            except Exception as e:
                print(f"Error loading {file}: {e}")

        # Load ERC1155 data
        print(f"Loading {len(erc1155_files)} ERC1155 files...")
        for file in erc1155_files:
            try:
                df = pd.read_csv(file)
                if len(df) > 0:
                    df['token_type'] = 'ERC1155'
                    all_transfers.append(df)
            except Exception as e:
                print(f"Error loading {file}: {e}")

        # Check if we have any data before concatenating
        if not all_transfers:
            raise ValueError(
                f"No data files found in {data_dir}. "
                f"Please ensure CSV files exist in erc20_minimal/, erc721_minimal/, or erc1155_minimal/ subdirectories."
            )

        # Combine all transfers
        transfers_df = pd.concat(all_transfers, ignore_index=True)
        print(f"✅ Loaded {len(transfers_df)} total transfers")

        # Get unique wallets
        all_wallets = pd.concat([transfers_df['from'], transfers_df['to']]).unique()
        all_wallets = [w for w in all_wallets if w != '0x0000000000000000000000000000000000000000']

        print(f"Extracting features for {len(all_wallets)} unique wallets...")

        # Extract features for each wallet
        wallet_features = []
        for wallet in all_wallets:
            features = self.extract_wallet_features(wallet, transfers_df)
            if features:
                # Add NFT count from ERC721/ERC1155
                nft_transfers = transfers_df[
                    (transfers_df['token_type'].isin(['ERC721', 'ERC1155'])) &
                    ((transfers_df['from'] == wallet) | (transfers_df['to'] == wallet))
                ]
                features['nft_txs'] = len(nft_transfers)
                features['nft_ratio'] = features['nft_txs'] / features['total_transactions'] if features['total_transactions'] > 0 else 0

                wallet_features.append(features)

        self.wallets_df = pd.DataFrame(wallet_features)
        print(f"✅ Extracted features for {len(self.wallets_df)} wallets")

        return self.wallets_df

    def create_embeddings(self, min_transactions: int = 5) -> Dict[str, np.ndarray]:
        """Create PCA and t-SNE embeddings"""

        if self.wallets_df is None:
            raise ValueError("No data loaded. Call load_and_process_minimal_data() first")

        # Filter wallets with minimum transactions
        filtered_df = self.wallets_df[self.wallets_df['total_transactions'] >= min_transactions].copy()
        print(f"Creating embeddings for {len(filtered_df)} wallets (min {min_transactions} transactions)...")

        # Select features for dimensionality reduction
        feature_cols = [
            'total_transactions',
            'unique_tokens',
            'unique_counterparties',
            'sent_ratio',
            'stablecoin_ratio',
            'meme_ratio',
            'defi_ratio',
            'wrapped_ratio',
            'nft_ratio',
            'activity_span_days'
        ]

        X = filtered_df[feature_cols].fillna(0).values

        # Scale features
        X_scaled = self.scaler.fit_transform(X)

        # PCA
        print("Computing PCA embeddings...")
        pca_coords = self.pca.fit_transform(X_scaled)

        # t-SNE
        print("Computing t-SNE embeddings (this may take a minute)...")
        tsne_coords = self.tsne.fit_transform(X_scaled)

        self.embeddings = {
            'pca': pca_coords,
            'tsne': tsne_coords
        }

        self.features_df = filtered_df.copy()
        self.features_df['pca_x'] = pca_coords[:, 0]
        self.features_df['pca_y'] = pca_coords[:, 1]
        self.features_df['tsne_x'] = tsne_coords[:, 0]
        self.features_df['tsne_y'] = tsne_coords[:, 1]

        print(f"✅ Created PCA and t-SNE embeddings")
        print(f"   PCA explained variance: {self.pca.explained_variance_ratio_.sum():.2%}")

        return self.embeddings

    def detect_behavior_communities(self) -> pd.DataFrame:
        """Detect behavior-based communities"""

        if self.features_df is None:
            raise ValueError("No embeddings created. Call create_embeddings() first")

        print("Detecting behavior-based communities...")

        # Assign community based on behavior
        self.features_df['community'] = self.features_df.apply(
            self.assign_behavior_community, axis=1
        )

        # Print community statistics
        community_stats = self.features_df['community'].value_counts()
        print(f"✅ Found {len(community_stats)} behavior communities:")
        for community, count in community_stats.items():
            print(f"   {community}: {count} wallets")

        return self.features_df

    def build_interaction_network(self, data_dir: str = None) -> nx.Graph:
        """Build wallet interaction network"""
        import os
        import glob
        
        # Determine data directory path dynamically if not provided
        if data_dir is None:
            # Get the backend directory (parent of src directory)
            current_file = os.path.abspath(__file__)
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
            data_dir = os.path.join(backend_dir, 'minimal_data')
        
        print(f"Building wallet interaction network from: {data_dir}")

        # Load all transfer data
        all_files = glob.glob(f'{data_dir}/**/*.csv', recursive=True)

        G = nx.Graph()
        edge_data = {}

        for file in all_files:
            try:
                df = pd.read_csv(file)
                for _, row in df.iterrows():
                    from_addr = row.get('from', '')
                    to_addr = row.get('to', '')

                    # Skip null addresses
                    if not from_addr or not to_addr or from_addr == '0x0000000000000000000000000000000000000000':
                        continue

                    edge_key = tuple(sorted([from_addr, to_addr]))

                    if edge_key in edge_data:
                        edge_data[edge_key]['weight'] += 1
                    else:
                        edge_data[edge_key] = {'weight': 1}
            except Exception as e:
                pass

        # Add edges to graph
        for (u, v), data in edge_data.items():
            G.add_edge(u, v, **data)

        print(f"✅ Network built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

        return G

    def export_for_frontend(self, network: nx.Graph = None) -> Dict:
        """Export all data for frontend visualization"""

        if self.features_df is None:
            raise ValueError("No analysis performed. Run the full pipeline first")

        print("Exporting data for frontend...")

        # Export wallet data with embeddings and communities
        wallets_data = self.features_df[[
            'address', 'total_transactions', 'unique_tokens', 'unique_counterparties',
            'stablecoin_ratio', 'meme_ratio', 'defi_ratio', 'wrapped_ratio', 'nft_ratio',
            'community', 'pca_x', 'pca_y', 'tsne_x', 'tsne_y'
        ]].to_dict('records')

        # Export network data
        network_data = None
        if network:
            # Only include wallets that are in our analyzed set
            analyzed_addresses = set(self.features_df['address'].tolist())

            nodes = []
            edges = []

            for node in network.nodes():
                if node in analyzed_addresses:
                    # Get community for this wallet
                    wallet_info = self.features_df[self.features_df['address'] == node].iloc[0]
                    nodes.append({
                        'id': node,
                        'community': wallet_info['community'],
                        'transactions': int(wallet_info['total_transactions'])
                    })

            node_ids = {node['id'] for node in nodes}

            for u, v, data in network.edges(data=True):
                if u in node_ids and v in node_ids:
                    edges.append({
                        'source': u,
                        'target': v,
                        'weight': data.get('weight', 1)
                    })

            network_data = {
                'nodes': nodes,
                'edges': edges
            }

        # Community statistics
        community_stats = self.features_df.groupby('community').agg({
            'total_transactions': 'sum',
            'address': 'count',
            'stablecoin_ratio': 'mean',
            'meme_ratio': 'mean',
            'defi_ratio': 'mean',
            'nft_ratio': 'mean'
        }).round(3).reset_index()

        community_stats.columns = ['community', 'total_txs', 'wallet_count',
                                    'avg_stablecoin_ratio', 'avg_meme_ratio',
                                    'avg_defi_ratio', 'avg_nft_ratio']

        export_data = {
            'wallets': wallets_data,
            'network': network_data,
            'community_stats': community_stats.to_dict('records'),
            'summary': {
                'total_wallets': len(self.features_df),
                'total_communities': self.features_df['community'].nunique(),
                'pca_explained_variance': float(self.pca.explained_variance_ratio_.sum())
            }
        }

        print(f"✅ Export complete")
        print(f"   {len(wallets_data)} wallets")
        print(f"   {len(export_data['community_stats'])} communities")
        if network_data:
            print(f"   {len(network_data['nodes'])} network nodes, {len(network_data['edges'])} edges")

        return export_data


def run_full_analysis(output_file: str = None):
    """Run the complete analysis pipeline"""
    import json
    import os

    # Determine output file path dynamically if not provided
    if output_file is None:
        # Get the backend directory (parent of src directory)
        current_file = os.path.abspath(__file__)
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
        output_file = os.path.join(backend_dir, 'data', 'results', 'visualization_data.json')

    analyzer = WalletBehaviorAnalyzer()

    # 1. Load and process data
    analyzer.load_and_process_minimal_data()

    # 2. Create embeddings
    analyzer.create_embeddings(min_transactions=5)

    # 3. Detect communities
    analyzer.detect_behavior_communities()

    # 4. Build network
    network = analyzer.build_interaction_network()

    # 5. Export for frontend
    export_data = analyzer.export_for_frontend(network)

    # 6. Save to file
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(export_data, f, indent=2)

    print(f"\n✅ Analysis complete! Data saved to {output_file}")

    return export_data


if __name__ == '__main__':
    run_full_analysis()
