"""Etherscan Data Collector"""
import os
import time
from typing import List, Dict
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()


class EtherscanCollector:
    """Collect transfer data from Etherscan API"""
    
    def __init__(self):
        self.api_key = os.getenv('ETHERSCAN_API_KEY', '')
        self.base_url = 'https://api.etherscan.io/api'
    
    def fetch_erc20_transfers(self, address: str, page: int = 1, offset: int = 100) -> pd.DataFrame:
        """Fetch ERC20 transfers for an address"""
        params = {
            'module': 'account',
            'action': 'tokentx',
            'address': address,
            'page': page,
            'offset': offset,
            'sort': 'desc',
            'apikey': self.api_key
        }
        
        try:
            response = requests.get(self.base_url, params=params, timeout=30)
            data = response.json()
            
            if data['status'] == '1' and data['result']:
                df = pd.DataFrame(data['result'])
                return df
            return pd.DataFrame()
            
        except Exception as e:
            print(f"❌ Error fetching ERC20 transfers: {e}")
            return pd.DataFrame()
    
    def fetch_erc721_transfers(self, address: str, page: int = 1, offset: int = 100) -> pd.DataFrame:
        """Fetch ERC721 (NFT) transfers for an address"""
        params = {
            'module': 'account',
            'action': 'tokennfttx',
            'address': address,
            'page': page,
            'offset': offset,
            'sort': 'desc',
            'apikey': self.api_key
        }
        
        try:
            response = requests.get(self.base_url, params=params, timeout=30)
            data = response.json()
            
            if data['status'] == '1' and data['result']:
                df = pd.DataFrame(data['result'])
                return df
            return pd.DataFrame()
            
        except Exception as e:
            print(f"❌ Error fetching ERC721 transfers: {e}")
            return pd.DataFrame()
    
    def fetch_all_transfers(self, address: str) -> Dict[str, pd.DataFrame]:
        """Fetch all types of transfers for an address"""
        print(f"Fetching transfers for {address[:10]}...")
        
        return {
            'erc20': self.fetch_erc20_transfers(address),
            'erc721': self.fetch_erc721_transfers(address),
        }