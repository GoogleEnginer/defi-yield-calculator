import asyncio
import aiohttp
import json
import math
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from web3 import Web3
from dataclasses import dataclass

@dataclass
class PoolInfo:
    protocol: str
    pool_address: str
    token0: str
    token1: str
    fee_tier: float
    tvl: float
    apr: float
    daily_volume: float

@dataclass
class YieldResult:
    daily_yield: float
    weekly_yield: float
    monthly_yield: float
    yearly_yield: float
    impermanent_loss: float
    fees_earned: float
    token_rewards: float

class DeFiYieldCalculator:
    def __init__(self, web3_provider: str = None):
        self.web3 = Web3(Web3.HTTPProvider(web3_provider)) if web3_provider else None
        self.protocols = {
            'uniswap_v3': {
                'name': 'Uniswap V3',
                'factory': '0x1F98431c8aD98523631AE4a59f267346ea31F984',
                'api_endpoint': 'https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3'
            },
            'sushiswap': {
                'name': 'SushiSwap',
                'factory': '0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac',
                'api_endpoint': 'https://api.thegraph.com/subgraphs/name/sushiswap/exchange'
            },
            'curve': {
                'name': 'Curve',
                'registry': '0x90E00ACe148ca3b23Ac1bC8C240C2a7Dd9c2d7f5',
                'api_endpoint': 'https://api.curve.fi/api/getPools/ethereum/main'
            }
        }
        
        self.token_prices = {}
        
    async def get_token_price(self, token_address: str) -> float:
        """获取代币价格"""
        if token_address.lower() in self.token_prices:
            return self.token_prices[token_address.lower()]
        
        # 使用CoinGecko API获取价格
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.coingecko.com/api/v3/simple/token_price/ethereum"
                params = {
                    'contract_addresses': token_address,
                    'vs_currencies': 'usd'
                }
                
                async with session.get(url, params=params) as response:
                    data = await response.json()
                    price = data.get(token_address.lower(), {}).get('usd', 0)
                    self.token_prices[token_address.lower()] = price
                    return price
        except Exception as e:
            print(f"获取代币价格失败: {e}")
            return 0

    async def get_uniswap_v3_pools(self, token0: str = None, token1: str = None) -> List[PoolInfo]:
        """获取Uniswap V3池子信息"""
        query = """
        {
            pools(first: 100, orderBy: totalValueLockedUSD, orderDirection: desc
                  where: {%s}) {
                id
                token0 {
                    id
                    symbol
                }
                token1 {
                    id
                    symbol
                }
                feeTier
                totalValueLockedUSD
                volumeUSD
                feeGrowthGlobal0X128
                feeGrowthGlobal1X128
            }
        }
        """
        
        where_clause = ""
        if token0 and token1:
            where_clause = f'token0: "{token0.lower()}", token1: "{token1.lower()}"'
        elif token0:
            where_clause = f'token0: "{token0.lower()}"'
        elif token1:
            where_clause = f'token1: "{token1.lower()}"'
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.protocols['uniswap_v3']['api_endpoint'],
                    json={'query': query % where_clause}
                ) as response:
                    data = await response.json()
                    
                    pools = []
                    for pool_data in data['data']['pools']:
                        # 计算APR
                        daily_volume = float(pool_data['volumeUSD'])
                        tvl = float(pool_data['totalValueLockedUSD'])
                        fee_tier = float(pool_data['feeTier']) / 10000  # 转换为百分比
                        
                        if tvl > 0:
                            daily_fee_revenue = daily_volume * fee_tier / 100
                            apr = (daily_fee_revenue * 365) / tvl * 100
                        else:
                            apr = 0
                        
                        pool = PoolInfo(
                            protocol='Uniswap V3',
                            pool_address=pool_data['id'],
                            token0=pool_data['token0']['symbol'],
                            token1=pool_data['token1']['symbol'],
                            fee_tier=fee_tier,
                            tvl=tvl,
                            apr=apr,
                            daily_volume=daily_volume
                        )
                        pools.append(pool)
                    
                    return pools
                    
        except Exception as e:
            print(f"获取Uniswap V3池子信息失败: {e}")
            return []

    async def get_curve_pools(self) -> List[PoolInfo]:
        """获取Curve池子信息"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.protocols['curve']['api_endpoint']) as response:
                    data = await response.json()
                    
                    pools = []
                    for pool_data in data['data']['poolData']:
                        # Curve池子通常有多个代币，这里简化处理
                        coins = pool_data.get('coins', [])
                        if len(coins) >= 2:
                            pool = PoolInfo(
                                protocol='Curve',
                                pool_address=pool_data['address'],
                                token0=coins[0]['symbol'],
                                token1=coins[1]['symbol'],
                                fee_tier=float(pool_data.get('fee', 0)) / 100,
                                tvl=float(pool_data.get('usdTotal', 0)),
                                apr=float(pool_data.get('apy', 0)),
                                daily_volume=float(pool_data.get('volumeUSD', 0))
                            )
                            pools.append(pool)
                    
                    return pools
                    
        except Exception as e:
            print(f"获取Curve池子信息失败: {e}")
            return []

    def calculate_impermanent_loss(self, price_change_ratio: float) -> float:
        """计算无常损失"""
        # 无常损失公式: IL = 2 * sqrt(price_ratio) / (1 + price_ratio) - 1
        if price_change_ratio <= 0:
            return 0
        
        sqrt_ratio = math.sqrt(price_change_ratio)
        il = 2 * sqrt_ratio / (1 + price_change_ratio) - 1
        return abs(il) * 100  # 转换为百分比

    async def calculate_yield(
        self, 
        pool: PoolInfo, 
        liquidity_amount: float,
        days: int = 30,
        token0_amount: float = None,
        token1_amount: float = None,
        price_change_projection: float = 1.0
    ) -> YieldResult:
        """计算流动性挖矿收益"""
        
        # 计算基础收益率
        daily_apr = pool.apr / 365
        
        # 计算手续费收益
        liquidity_share = liquidity_amount / pool.tvl if pool.tvl > 0 else 0
        daily_fee_revenue = pool.daily_volume * (pool.fee_tier / 100) * liquidity_share
        
        # 计算时间周期收益
        daily_yield = liquidity_amount * (daily_apr / 100)
        weekly_yield = daily_yield * 7
        monthly_yield = daily_yield * 30
        yearly_yield = daily_yield * 365
        
        # 计算无常损失
        impermanent_loss = self.calculate_impermanent_loss(price_change_projection)
        
        # 计算净收益（考虑无常损失）
        total_yield = daily_yield * days
        net_yield = total_yield - (liquidity_amount * impermanent_loss / 100)
        
        return YieldResult(
            daily_yield=daily_yield + daily_fee_revenue,
            weekly_yield=weekly_yield + (daily_fee_revenue * 7),
            monthly_yield=monthly_yield + (daily_fee_revenue * 30),
            yearly_yield=yearly_yield + (daily_fee_revenue * 365),
            impermanent_loss=impermanent_loss,
            fees_earned=daily_fee_revenue * days,
            token_rewards=0  # 需要根据具体协议计算代币奖励
        )

    async def compare_pools(
        self, 
        pools: List[PoolInfo], 
        liquidity_amount: float,
        days: int = 30
    ) -> pd.DataFrame:
        """比较不同池子的收益"""
        results = []
        
        for pool in pools:
            yield_result = await self.calculate_yield(pool, liquidity_amount, days)
            
            results.append({
                'Protocol': pool.protocol,
                'Pool': f"{pool.token0}/{pool.token1}",
                'Fee Tier': f"{pool.fee_tier}%",
                'TVL': f"${pool.tvl:,.0f}",
                'APR': f"{pool.apr:.2f}%",
                'Daily Volume': f"${pool.daily_volume:,.0f}",
                'Daily Yield': f"${yield_result.daily_yield:.2f}",
                'Monthly Yield': f"${yield_result.monthly_yield:.2f}",
                'Yearly Yield': f"${yield_result.yearly_yield:.2f}",
                'Impermanent Loss': f"{yield_result.impermanent_loss:.2f}%",
                'Net Monthly Return': f"${yield_result.monthly_yield - (liquidity_amount * yield_result.impermanent_loss / 100 / 12):.2f}"
            })
        
        return pd.DataFrame(results)

    async def simulate_yield_scenarios(
        self,
        pool: PoolInfo,
        liquidity_amount: float,
        price_changes: List[float] = None
    ) -> Dict:
        """模拟不同价格变动场景下的收益"""
        if price_changes is None:
            price_changes = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0]  # 50%下跌到100%上涨
        
        scenarios = {}
        
        for price_change in price_changes:
            yield_result = await self.calculate_yield(
                pool, 
                liquidity_amount, 
                days=30,
                price_change_projection=price_change
            )
            
            scenario_name = f"Price Change: {(price_change - 1) * 100:+.0f}%"
            scenarios[scenario_name] = {
                'Monthly Yield': yield_result.monthly_yield,
                'Impermanent Loss': yield_result.impermanent_loss,
                'Net Return': yield_result.monthly_yield - (liquidity_amount * yield_result.impermanent_loss / 100),
                'ROI': ((yield_result.monthly_yield - (liquidity_amount * yield_result.impermanent_loss / 100)) / liquidity_amount) * 100
            }
        
        return scenarios

    def calculate_optimal_range(
        self, 
        current_price: float, 
        volatility: float, 
        days: int = 30
    ) -> Tuple[float, float]:
        """计算Uniswap V3最优价格区间"""
        # 基于历史波动率计算合理的价格区间
        # 使用1个标准差作为区间
        price_std = current_price * volatility / math.sqrt(365) * math.sqrt(days)
        
        lower_price = current_price - (2 * price_std)
        upper_price = current_price + (2 * price_std)
        
        return max(lower_price, current_price * 0.5), min(upper_price, current_price * 2.0)

    async def get_historical_performance(
        self,
        pool_address: str,
        days: int = 30
    ) -> Dict:
        """获取池子历史表现数据"""
        # 这里需要实现具体的历史数据获取逻辑
        # 可以从The Graph或其他数据源获取
        pass

    def generate_yield_report(
        self,
        pool: PoolInfo,
        yield_result: YieldResult,
        liquidity_amount: float
    ) -> str:
