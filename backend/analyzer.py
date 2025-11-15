#!/usr/bin/env python3
"""
Data Analyzer CLI
Analyze wallet data using ML techniques
"""

import argparse
from pathlib import Path
import pandas as pd
import json

from src.ml import WalletClusterer, AnomalyDetector, NetworkAnalyzer


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
  # Run clustering
  python analyzer.py --input data/processed/wallets.csv --clustering
  
  # Detect anomalies
  python analyzer.py --input data/processed/wallets.csv --anomaly
  
  # Network analysis
  python analyzer.py --input data/processed/transfers.csv --network
  
  # Run all analyses
  python analyzer.py --input data/processed/wallets.csv --all
        """
    )
    
    parser.add_argument('--input', type=str, required=True, help='Input CSV file')
    parser.add_argument('--clustering', action='store_true', help='Run clustering analysis')
    parser.add_argument('--anomaly', action='store_true', help='Detect anomalies')
    parser.add_argument('--network', action='store_true', help='Network analysis')
    parser.add_argument('--all', action='store_true', help='Run all analyses')
    parser.add_argument('--output', type=str, default='data/results', help='Output directory')
    parser.add_argument('--n-clusters', type=int, default=5, help='Number of clusters')
    
    args = parser.parse_args()
    
    # Load data
    df = load_csv(args.input)
    
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
        graph = analyzer.build_graph(df)
        
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