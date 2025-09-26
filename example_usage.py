import asyncio
from src.yield_calculator import DeFiYieldCalculator

async def main():
    calculator = DeFiYieldCalculator(
        web3_provider="https://mainnet.infura.io/v3/YOUR_INFURA_KEY"
    )
    
    # 获取Uniswap V3热门池子
    print("获取Uniswap V3池子信息...")
    uniswap_pools = await calculator.get_uniswap_v3_pools()
    
    if uniswap_pools:
        # 选择TVL最高的池子进行分析
        top_pool = max(uniswap_pools, key=lambda x: x.tvl)
        print(f"分析池子: {top_pool.token0}/{top_pool.token1}")
        
        # 计算10000美元投资的收益
        liquidity_amount = 10000
        yield_result = await calculator.calculate_yield(top_pool, liquidity_amount)
        
        # 生成报告
        report = calculator.generate_yield_report(top_pool, yield_result, liquidity_amount)
        print(report)
        
        # 比较多个池子
        top_pools = sorted(uniswap_pools, key=lambda x: x.tvl, reverse=True)[:5]
        comparison = await calculator.compare_pools(top_pools, liquidity_amount)
        print("\n=== 池子收益对比 ===")
        print(comparison.to_string(index=False))
        
        # 价格变动场景分析
        scenarios = await calculator.simulate_yield_scenarios(top_pool, liquidity_amount)
        print("\n=== 价格变动场景分析 ===")
        for scenario, results in scenarios.items():
            print(f"{scenario}: ROI {results['ROI']:.2f}%, 净收益 ${results['Net Return']:.2f}")

if __name__ == "__main__":
    asyncio.run(main())
