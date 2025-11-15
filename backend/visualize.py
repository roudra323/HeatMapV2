#!/usr/bin/env python3
"""
Wallet Behavior Visualization CLI

Run complete analysis on minimal data and generate visualization-ready export
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from src.ml.visualizer import WalletBehaviorAnalyzer, run_full_analysis


def main():
    # Determine default output path dynamically
    backend_dir = os.path.dirname(__file__)
    default_output = os.path.join(backend_dir, 'data', 'results', 'visualization_data.json')
    
    parser = argparse.ArgumentParser(description='Wallet Behavior Visualization')
    parser.add_argument(
        '--output',
        default=default_output,
        help='Output JSON file path'
    )
    parser.add_argument(
        '--min-transactions',
        type=int,
        default=5,
        help='Minimum transactions for a wallet to be included'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Wallet Behavior Visualization Analysis")
    print("=" * 60)
    print(f"Output: {args.output}")
    print(f"Min transactions: {args.min_transactions}")
    print("=" * 60)
    print()

    try:
        # Run full analysis
        export_data = run_full_analysis(output_file=args.output)

        print("\n" + "=" * 60)
        print("✅ SUCCESS!")
        print("=" * 60)
        print(f"Analyzed {export_data['summary']['total_wallets']} wallets")
        print(f"Detected {export_data['summary']['total_communities']} behavior communities")
        print(f"PCA explained variance: {export_data['summary']['pca_explained_variance']:.1%}")
        print(f"\nData exported to: {args.output}")
        print("\nCommunity Distribution:")
        for stat in export_data['community_stats']:
            print(f"  {stat['community']}: {stat['wallet_count']} wallets")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
