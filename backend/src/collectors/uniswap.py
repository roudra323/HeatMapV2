"""Uniswap Data Collector"""
import os
from typing import List, Dict
from subgrounds import Subgrounds
import pandas as pd
from dotenv import load_dotenv

load_dotenv()


class UniswapCollector:
    """Collect trading data from Uniswap v3"""
    
    def __init__(self):
        self.sg = Subgrounds()
        self.uniswap = self.sg.load_subgraph(
            'https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3'
        )
    
    def fetch_trades(self, limit: int = 1000, skip: int = 0) -> pd.DataFrame:
        """
        Fetch recent Uniswap trades
        
        Args:
            limit: Maximum number of trades to fetch
            skip: Number of trades to skip
            
        Returns:
            DataFrame with trade data
        """
        print(f"Fetching {limit} Uniswap trades (skip: {skip})...")
        
        try:
            swaps = self.uniswap.Query.swaps(
                first=limit,
                skip=skip,
                orderBy=self.uniswap.Swap.timestamp,
                orderDirection='desc'
            )
            
            df = self.sg.query_df([
                swaps.id,
                swaps.timestamp,
                swaps.sender,
                swaps.recipient,
                swaps.amount0,
                swaps.amount1,
                swaps.amountUSD,
                swaps.token0.symbol,
                swaps.token1.symbol,
            ])
            
            print(f"✅ Fetched {len(df)} trades")
            return df
            
        except Exception as e:
            print(f"❌ Error fetching Uniswap data: {e}")
            return pd.DataFrame()
    
    def get_unique_wallets(self, trades_df: pd.DataFrame) -> List[str]:
        """Extract unique wallet addresses from trades"""
        wallets = set()
        
        if 'swaps_sender' in trades_df.columns:
            wallets.update(trades_df['swaps_sender'].dropna().unique())
        if 'swaps_recipient' in trades_df.columns:
            wallets.update(trades_df['swaps_recipient'].dropna().unique())
        
        return list(wallets)