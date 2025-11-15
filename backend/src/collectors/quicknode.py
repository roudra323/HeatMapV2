"""QuickNode Wallet Validator"""
import os
from typing import List, Dict
import requests
from dotenv import load_dotenv

load_dotenv()


class QuickNodeCollector:
    """Validate if addresses are wallets or contracts using QuickNode"""
    
    def __init__(self):
        self.endpoint = os.getenv('QUICKNODE_API_KEY', '')
    
    def is_contract(self, address: str) -> bool:
        """Check if an address is a contract"""
        if not self.endpoint:
            return False
        
        payload = {
            "method": "eth_getCode",
            "params": [address, "latest"],
            "id": 1,
            "jsonrpc": "2.0"
        }
        
        try:
            response = requests.post(self.endpoint, json=payload, timeout=10)
            result = response.json().get('result', '0x')
            # If code exists, it's a contract
            return result != '0x'
        except:
            return False
    
    def validate_wallets(self, addresses: List[str]) -> List[Dict[str, any]]:
        """Validate a list of addresses"""
        results = []
        
        for i, address in enumerate(addresses):
            if i % 10 == 0:
                print(f"Validated {i}/{len(addresses)} addresses...")
            
            is_contract = self.is_contract(address)
            results.append({
                'address': address,
                'is_wallet': not is_contract,
                'is_contract': is_contract
            })
        
        print(f"✅ Validated {len(results)} addresses")
        return results