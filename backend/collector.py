#!/usr/bin/env python3
"""
Data Collector CLI
Collect blockchain data from various sources
"""

import argparse
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

from src.collectors import UniswapCollector, EtherscanCollector, QuickNodeCollector

load_dotenv()


def save_csv(df: pd.DataFrame, filepath: str):
    """Save DataFrame to CSV"""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(filepath, index=False)
    print(f"💾 Saved to {filepath}")


def main():
    parser = argparse.ArgumentParser(
        description='Collect blockchain data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch Uniswap trades
  python collector.py --uniswap --limit 500
  
  # Fetch transfers for a wallet
  python collector.py --transfers 0x1234...
  
  # Validate wallet addresses
  python collector.py --validate wallets.txt
        """
    )
    
    parser.add_argument('--uniswap', action='store_true', help='Fetch Uniswap trades')
    parser.add_argument('--transfers', type=str, help='Fetch transfers for wallet address')
    parser.add_argument('--validate', type=str, help='Validate addresses from file')
    parser.add_argument('--limit', type=int, default=1000, help='Max records to fetch')
    parser.add_argument('--output', type=str, default='data/raw', help='Output directory')
    
    args = parser.parse_args()
    
    if args.uniswap:
        print("\n📊 Fetching Uniswap Trades...")
        collector = UniswapCollector()
        trades = collector.fetch_trades(limit=args.limit)
        
        if not trades.empty:
            save_csv(trades, f"{args.output}/uniswap_trades.csv")
            
            # Extract unique wallets
            wallets = collector.get_unique_wallets(trades)
            wallet_df = pd.DataFrame({'address': wallets})
            save_csv(wallet_df, f"{args.output}/uniswap_wallets.csv")
            print(f"✅ Extracted {len(wallets)} unique wallets")
    
    elif args.transfers:
        print(f"\n📊 Fetching Transfers for {args.transfers[:10]}...")
        collector = EtherscanCollector()
        transfers = collector.fetch_all_transfers(args.transfers)
        
        for token_type, df in transfers.items():
            if not df.empty:
                filename = f"{args.output}/transfers_{args.transfers[:10]}_{token_type}.csv"
                save_csv(df, filename)
    
    elif args.validate:
        print(f"\n🔍 Validating Addresses from {args.validate}...")
        
        # Load addresses
        with open(args.validate, 'r') as f:
            addresses = [line.strip() for line in f if line.strip()]
        
        collector = QuickNodeCollector()
        results = collector.validate_wallets(addresses)
        
        df = pd.DataFrame(results)
        save_csv(df, f"{args.output}/validated_wallets.csv")
        
        wallets = df[df['is_wallet'] == True]
        print(f"✅ Found {len(wallets)} wallets out of {len(df)} addresses")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()