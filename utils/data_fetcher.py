import aiohttp
import asyncio
from typing import Dict, List

class DataFetcher:
    def __init__(self):
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def fetch_multiple_token_prices(self, token_addresses: List[str]) -> Dict[str, float]:
        """批量获取代币价格"""
        url = "https://api.coingecko.com/api/v3/simple/token_price/ethereum"
        params = {
            'contract_addresses': ','.join(token_addresses),
            'vs_currencies': 'usd'
        }
        
        try:
            async with self.session.get(url, params=params) as response:
                data = await response.json()
                return {addr: info.get('usd', 0) for addr, info in data.items()}
        except Exception as e:
            print(f"获取代币价格失败: {e}")
            return {}
