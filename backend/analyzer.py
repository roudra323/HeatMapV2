#!/usr/bin/env python3
"""
Data Analyzer CLI
Analyze wallet data using ML techniques
"""

import argparse
from pathlib import Path
import pandas as pd
import json
import yaml

from src.ml import WalletClusterer, AnomalyDetector, NetworkAnalyzer


def load_config() -> dict:
    """Load configuration from config file"""
    config_path = Path(__file__).parent / "config" / "base.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def aggregate_transfers_to_wallets(transfers_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate transfer-level data into wallet-level features for ML analysis
    
    Args:
        transfers_df: DataFrame with transfer data (from, to, timeStamp, etc.)
    
    Returns:
        DataFrame with wallet-level aggregated features
    """
    print("🔄 Aggregating transfers into wallet features...")
    
    # Get all unique wallet addresses (both from and to)
    all_addresses = set()
    if 'from' in transfers_df.columns:
        all_addresses.update(transfers_df['from'].dropna().unique())
    if 'to' in transfers_df.columns:
        all_addresses.update(transfers_df['to'].dropna().unique())
    
    wallet_features = []
    
    for address in all_addresses:
        # Filter transfers involving this wallet
        wallet_transfers = transfers_df[
            (transfers_df['from'] == address) | (transfers_df['to'] == address)
        ]
        
        if len(wallet_transfers) == 0:
            continue
        
        # Calculate features
        transaction_count = len(wallet_transfers)
        
        # Count unique tokens
        unique_tokens = set()
        if 'tokenSymbol' in wallet_transfers.columns:
            unique_tokens.update(wallet_transfers['tokenSymbol'].dropna().unique())
        if 'tokenName' in wallet_transfers.columns:
            unique_tokens.update(wallet_transfers['tokenName'].dropna().unique())
        
        # Count unique counterparties
        unique_counterparties = set()
        if 'from' in wallet_transfers.columns:
            unique_counterparties.update(wallet_transfers[wallet_transfers['to'] == address]['from'].dropna().unique())
        if 'to' in wallet_transfers.columns:
            unique_counterparties.update(wallet_transfers[wallet_transfers['from'] == address]['to'].dropna().unique())
        
        # For volume, we'll use transaction count as proxy since we don't have value column
        # In real data, you'd sum the 'value' column
        total_volume = transaction_count  # Placeholder - adjust based on actual data structure
        avg_transaction_value = total_volume / transaction_count if transaction_count > 0 else 0
        
        wallet_features.append({
            'address': address,
            'transaction_count': transaction_count,
            'total_volume': total_volume,
            'avg_transaction_value': avg_transaction_value,
            'unique_tokens': len(unique_tokens),
            'unique_counterparties': len(unique_counterparties),
        })
    
    result_df = pd.DataFrame(wallet_features)
    print(f"✅ Aggregated {len(result_df)} wallets from {len(transfers_df)} transfers")
    
    return result_df


def load_minimal_data(data_path: Path, token_types: list = ['erc20', 'erc721', 'erc1155']) -> pd.DataFrame:
    """
    Load and aggregate minimal test data from minimal_data directory
    
    Args:
        data_path: Path to minimal_data directory
        token_types: List of token types to load (erc20, erc721, erc1155)
    
    Returns:
        Combined DataFrame with all transfer data
    """
    all_data = []
    
    for token_type in token_types:
        token_dir = data_path / f"{token_type}_minimal"
        
        if not token_dir.exists():
            print(f"⚠️  Directory not found: {token_dir}")
            continue
        
        # Load all CSV files in the directory
        csv_files = list(token_dir.glob("*.csv"))
        print(f"📂 Loading {len(csv_files)} {token_type} files...")
        
        for csv_file in csv_files:
            try:
                df = pd.read_csv(csv_file)
                # Add token type column
                df['token_type'] = token_type
                all_data.append(df)
            except Exception as e:
                print(f"⚠️  Error loading {csv_file.name}: {e}")
    
    if not all_data:
        print("❌ No minimal data found")
        return pd.DataFrame()
    
    # Combine all DataFrames
    combined_df = pd.concat(all_data, ignore_index=True)
    print(f"✅ Loaded {len(combined_df)} total records from minimal data")
    
    return combined_df


def load_csv(filepath: str) -> pd.DataFrame:
    """Load CSV file"""
    df = pd.read_csv(filepath)
    print(f"📂 Loaded {len(df)} records from {filepath}")
    return df


def save_csv(df: pd.DataFrame, filepath: str):
    """Save DataFrame to CSV"""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(filepath, index=False)
    print(f"💾 Saved to {filepath}")


def save_json(data: dict, filepath: str):
    """Save data to JSON"""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"💾 Saved to {filepath}")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze blockchain wallet data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use minimal test data (from config)
  python analyzer.py --use-minimal --clustering
  
  # Use minimal test data for all analyses
  python analyzer.py --use-minimal --all
  
  # Use specific input file
  python analyzer.py --input data/processed/wallets.csv --clustering
  
  # Detect anomalies
  python analyzer.py --input data/processed/wallets.csv --anomaly
  
  # Network analysis
  python analyzer.py --input data/processed/transfers.csv --network
        """
    )
    
    parser.add_argument('--input', type=str, help='Input CSV file (optional if using minimal data)')
    parser.add_argument('--clustering', action='store_true', help='Run clustering analysis')
    parser.add_argument('--anomaly', action='store_true', help='Detect anomalies')
    parser.add_argument('--network', action='store_true', help='Network analysis')
    parser.add_argument('--all', action='store_true', help='Run all analyses')
    parser.add_argument('--output', type=str, default='data/results', help='Output directory')
    parser.add_argument('--n-clusters', type=int, default=5, help='Number of clusters')
    parser.add_argument('--use-minimal', action='store_true', help='Use minimal test data (overrides config)')
    
    args = parser.parse_args()
    
    # Load config
    config = load_config()
    analyzer_config = config.get('analyzer', {})
    use_minimal = args.use_minimal or analyzer_config.get('use_minimal_data', False)
    
    # Load data
    transfers_df = None
    if use_minimal:
        minimal_path = Path(__file__).parent / analyzer_config.get('minimal_data_path', 'minimal_data')
        transfers_df = load_minimal_data(minimal_path)
        if transfers_df.empty:
            print("❌ Failed to load minimal data. Exiting.")
            return
        # Aggregate transfer data into wallet-level features for clustering/anomaly
        df = aggregate_transfers_to_wallets(transfers_df)
        if df.empty:
            print("❌ Failed to aggregate wallet features. Exiting.")
            return
    elif args.input:
        df = load_csv(args.input)
    else:
        parser.error("Either --input or --use-minimal must be specified")
    
    # Run all if specified
    if args.all:
        args.clustering = True
        args.anomaly = True
        args.network = True
    
    # Clustering
    if args.clustering:
        print("\n🎯 Running Clustering Analysis...")
        clusterer = WalletClusterer(n_clusters=args.n_clusters)
        result = clusterer.fit_predict(df)
        save_csv(result, f"{args.output}/clusters.csv")
    
    # Anomaly Detection
    if args.anomaly:
        print("\n🔍 Running Anomaly Detection...")
        detector = AnomalyDetector()
        result = detector.detect(df)
        save_csv(result, f"{args.output}/anomalies.csv")
        
        # Save only anomalies
        anomalies = result[result['is_anomaly'] == True]
        save_csv(anomalies, f"{args.output}/anomalies_only.csv")
    
    # Network Analysis
    if args.network:
        print("\n🕸️  Running Network Analysis...")
        analyzer = NetworkAnalyzer()
        # Network analysis needs raw transfer data, not aggregated wallet data
        network_df = transfers_df if transfers_df is not None else df
        graph = analyzer.build_graph(network_df)
        
        # Calculate metrics
        metrics = analyzer.calculate_metrics()
        save_csv(metrics, f"{args.output}/network_metrics.csv")
        
        # Find communities
        communities = analyzer.find_communities()
        comm_df = pd.DataFrame([
            {'address': addr, 'community': comm_id}
            for addr, comm_id in communities.items()
        ])
        save_csv(comm_df, f"{args.output}/communities.csv")
        
        # Export for visualization
        viz_data = analyzer.export_for_visualization()
        save_json(viz_data, f"{args.output}/network.json")
    
    print("\n✅ Analysis complete!")


if __name__ == "__main__":
    main()