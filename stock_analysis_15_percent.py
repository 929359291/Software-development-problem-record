"""
A股市场复合年化收益率超过15%的股票分析工具
该脚本从公开市场数据中筛选年化收益率超过15%的股票，并输出详细分析指标到Excel文件
"""

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

warnings.filterwarnings('ignore')

def get_single_stock_performance(ts_code, name, start_date, end_date):
    """
    获取单个股票的性能数据
    包括年化收益率、总收益率、波动率、夏普比率等关键指标
    """
    try:
        # 获取股票历史数据（后复权）用于技术指标计算
        df_hfq = ak.stock_zh_a_hist(symbol=ts_code, period="daily", start_date=start_date, end_date=end_date, adjust="hfq")

        if df_hfq.empty or len(df_hfq) < 250:  # 至少需要一年的日线数据
            return None

        df_hfq = df_hfq.sort_values('日期').reset_index(drop=True)

        # 获取前复权数据用于获取最新真实股价
        df_qfq = ak.stock_zh_a_hist(symbol=ts_code, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        
        if df_qfq.empty:
            return None
            
        df_qfq = df_qfq.sort_values('日期').reset_index(drop=True)

        # 获取起始和结束价格（使用后复权数据计算技术指标）
        start_price = df_hfq.iloc[0]['收盘']
        end_price_hfq = df_hfq.iloc[-1]['收盘']  # 用于计算技术指标的后复权价格

        # 获取最新真实股价（使用前复权数据）
        latest_real_price = df_qfq.iloc[-1]['收盘']  # 最新真实股价

        if start_price <= 0:
            return None

        # 计算时间跨度
        actual_start_date = pd.to_datetime(df_hfq.iloc[0]['日期'])
        actual_end_date = pd.to_datetime(df_hfq.iloc[-1]['日期'])
        years = (actual_end_date - actual_start_date).days / 365.25

        if years < 15:  # 调整为至少2年数据，以提高数据可用性
            return None

        # 计算各种指标（使用后复权数据）
        total_return = (end_price_hfq - start_price) / start_price
        annualized_return = (end_price_hfq / start_price) ** (1 / years) - 1

        # 计算波动率（使用后复权数据）
        df_hfq['daily_return'] = df_hfq['收盘'].pct_change()
        volatility = df_hfq['daily_return'].std() * np.sqrt(244)  # 年化波动率

        # 计算最大回撤（使用后复权数据）
        df_hfq['cumulative_return'] = (1 + df_hfq['daily_return']).cumprod()
        df_hfq['rolling_max'] = df_hfq['cumulative_return'].expanding().max()
        df_hfq['drawdown'] = (df_hfq['cumulative_return'] - df_hfq['rolling_max']) / df_hfq['rolling_max']
        max_drawdown = abs(df_hfq['drawdown'].min())

        # 计算胜率（正收益天数比例，使用后复权数据）
        positive_returns = len(df_hfq[df_hfq['daily_return'] > 0])
        total_trading_days = len(df_hfq.dropna(subset=['daily_return']))
        win_rate = positive_returns / total_trading_days if total_trading_days > 0 else 0

        # 获取财务指标
        avg_debt_to_asset = None
        avg_roe = None
        latest_net_profit = None
        latest_net_profit_growth = None
        
        try:
            # 尝试获取财务指标
            # 优先使用同花顺财务指标
            try:
                fina_indicator_df = ak.stock_financial_abstract_ths(symbol=ts_code)
                if fina_indicator_df is not None and not fina_indicator_df.empty and len(fina_indicator_df) > 0:
                    # 按报告期排序
                    fina_indicator_df = fina_indicator_df.sort_values('报告期').reset_index(drop=True)
                    
                    # 获取最近几年的资产负债率和净资产收益率
                    recent_years_data = fina_indicator_df.tail(5)  # 获取最近5年的数据
                    
                    debt_to_asset_list = []
                    roe_list = []
                    
                    for idx, row in recent_years_data.iterrows():
                        # 获取资产负债率
                        debt_to_asset_val = row.get('资产负债率')
                        if debt_to_asset_val is not None and pd.notna(debt_to_asset_val) and debt_to_asset_val != '-' and debt_to_asset_val != '':
                            try:
                                # 去掉百分号并转换为数值
                                val_str = str(debt_to_asset_val).strip()
                                if val_str.endswith('%'):
                                    val = float(val_str.replace('%', '')) / 100
                                else:
                                    val = float(val_str)
                                debt_to_asset_list.append(val)
                            except (ValueError, AttributeError):
                                continue
                        
                        # 获取净资产收益率-摊薄（相当于ROE）
                        roe_val = row.get('净资产收益率-摊薄')
                        if roe_val is not None and pd.notna(roe_val) and roe_val != '-' and roe_val != '':
                            try:
                                # 去掉百分号并转换为数值
                                val_str = str(roe_val).strip()
                                if val_str.endswith('%'):
                                    val = float(val_str.replace('%', '')) / 100
                                else:
                                    val = float(val_str)
                                roe_list.append(val)
                            except (ValueError, AttributeError):
                                continue
                    
                    # 计算平均值
                    if debt_to_asset_list:
                        avg_debt_to_asset = np.mean(debt_to_asset_list)
                    if roe_list:
                        avg_roe = np.mean(roe_list)
                    
                    # 获取最近一年的净利润和净利润同比增长率
                    latest_row = fina_indicator_df.iloc[-1] if len(fina_indicator_df) > 0 else None
                    if latest_row is not None:
                        # 获取净利润
                        net_profit_col = None
                        for col in ['净利润', '净利润-净利润', '归属母公司股东的净利润']:
                            if col in latest_row.index:
                                net_profit_col = col
                                break
                        
                        if net_profit_col:
                            net_profit_val = latest_row[net_profit_col]
                            if net_profit_val is not None and pd.notna(net_profit_val) and net_profit_val != '-' and net_profit_val != '':
                                try:
                                    val_str = str(net_profit_val).strip()
                                    if val_str.endswith('万') or val_str.endswith('亿'):
                                        # 处理金额单位
                                        multiplier = 1
                                        if val_str.endswith('万'):
                                            multiplier = 10000
                                            val_str = val_str[:-1]
                                        elif val_str.endswith('亿'):
                                            multiplier = 100000000
                                            val_str = val_str[:-1]
                                        
                                        try:
                                            latest_net_profit = float(val_str) * multiplier
                                        except ValueError:
                                            latest_net_profit = None
                                    else:
                                        latest_net_profit = float(val_str)
                                except (ValueError, TypeError):
                                    latest_net_profit = None
                        
                        # 获取净利润同比增长率
                        net_profit_growth_col = None
                        for col in ['净利润同比增长率', '净利润-同比增长率', '归属母公司股东的净利润同比增长率']:
                            if col in latest_row.index:
                                net_profit_growth_col = col
                                break
                        
                        if net_profit_growth_col:
                            growth_val = latest_row[net_profit_growth_col]
                            if growth_val is not None and pd.notna(growth_val) and growth_val != '-' and growth_val != '':
                                try:
                                    val_str = str(growth_val).strip()
                                    if val_str.endswith('%'):
                                        latest_net_profit_growth = float(val_str.replace('%', ''))
                                    else:
                                        latest_net_profit_growth = float(val_str)
                                except (ValueError, TypeError):
                                    latest_net_profit_growth = None
            except Exception as e:
                print(f"同花顺财务指标获取失败 {ts_code}: {str(e)}")
                pass
            
            # 如果上述方法获取的数据不足，尝试使用其他接口
            if avg_debt_to_asset is None or avg_roe is None or latest_net_profit is None or latest_net_profit_growth is None:
                try:
                    # 尝试东方财富财务分析指标
                    em_fina_df = ak.stock_financial_analysis_indicator_em(symbol=ts_code)
                    if em_fina_df is not None and not em_fina_df.empty and len(em_fina_df) > 0:
                        # 按报告期排序
                        em_fina_df = em_fina_df.sort_values('报告期').reset_index(drop=True)
                        
                        recent_years_data = em_fina_df.tail(5)  # 获取最近5年的数据
                        
                        em_debt_to_asset_list = []
                        em_roe_list = []
                        
                        for idx, row in recent_years_data.iterrows():
                            # 获取资产负债率
                            if avg_debt_to_asset is None:
                                debt_to_asset_val = row.get('资产负债率')
                                if debt_to_asset_val is not None and pd.notna(debt_to_asset_val) and debt_to_asset_val != '-' and debt_to_asset_val != '':
                                    try:
                                        val_str = str(debt_to_asset_val).strip()
                                        if val_str.endswith('%'):
                                            val = float(val_str.replace('%', '')) / 100
                                        else:
                                            val = float(val_str)
                                        em_debt_to_asset_list.append(val)
                                    except (ValueError, AttributeError):
                                        pass
                            
                            # 获取ROE
                            if avg_roe is None:
                                roe_val = row.get('净资产收益率')
                                if roe_val is not None and pd.notna(roe_val) and roe_val != '-' and roe_val != '':
                                    try:
                                        val_str = str(roe_val).strip()
                                        if val_str.endswith('%'):
                                            val = float(val_str.replace('%', '')) / 100
                                        else:
                                            val = float(val_str)
                                        em_roe_list.append(val)
                                    except (ValueError, AttributeError):
                                        pass
                        
                        if avg_debt_to_asset is None and em_debt_to_asset_list:
                            avg_debt_to_asset = np.mean(em_debt_to_asset_list)
                        if avg_roe is None and em_roe_list:
                            avg_roe = np.mean(em_roe_list)
                        
                        # 获取最近一年的净利润和净利润同比增长率
                        if latest_net_profit is None or latest_net_profit_growth is None:
                            latest_row = em_fina_df.iloc[-1] if len(em_fina_df) > 0 else None
                            if latest_row is not None:
                                # 获取净利润
                                if latest_net_profit is None:
                                    net_profit_col = None
                                    for col in ['净利润', '净利润-净利润', '归属母公司股东的净利润']:
                                        if col in latest_row.index:
                                            net_profit_col = col
                                            break
                                    
                                    if net_profit_col:
                                        net_profit_val = latest_row[net_profit_col]
                                        if net_profit_val is not None and pd.notna(net_profit_val) and net_profit_val != '-' and net_profit_val != '':
                                            try:
                                                val_str = str(net_profit_val).strip()
                                                if val_str.endswith('万') or val_str.endswith('亿'):
                                                    # 处理金额单位
                                                    multiplier = 1
                                                    if val_str.endswith('万'):
                                                        multiplier = 10000
                                                        val_str = val_str[:-1]
                                                    elif val_str.endswith('亿'):
                                                        multiplier = 100000000
                                                        val_str = val_str[:-1]
                                                    
                                                    try:
                                                        latest_net_profit = float(val_str) * multiplier
                                                    except ValueError:
                                                        latest_net_profit = None
                                                else:
                                                    latest_net_profit = float(val_str)
                                            except (ValueError, TypeError):
                                                latest_net_profit = None
                                
                                # 获取净利润同比增长率
                                if latest_net_profit_growth is None:
                                    net_profit_growth_col = None
                                    for col in ['净利润同比增长率', '净利润-同比增长率', '归属母公司股东的净利润同比增长率']:
                                        if col in latest_row.index:
                                            net_profit_growth_col = col
                                            break
                                    
                                    if net_profit_growth_col:
                                        growth_val = latest_row[net_profit_growth_col]
                                        if growth_val is not None and pd.notna(growth_val) and growth_val != '-' and growth_val != '':
                                            try:
                                                val_str = str(growth_val).strip()
                                                if val_str.endswith('%'):
                                                    latest_net_profit_growth = float(val_str.replace('%', ''))
                                                else:
                                                    latest_net_profit_growth = float(val_str)
                                            except (ValueError, TypeError):
                                                latest_net_profit_growth = None
                except Exception as e:
                    print(f"东方财富财务指标获取失败 {ts_code}: {str(e)}")
                    pass

        except Exception as fe:
            print(f"获取财务数据时出错 {ts_code}: {str(fe)}")

        return {
            'ts_code': ts_code,
            'name': name,
            'start_date': actual_start_date.strftime('%Y-%m-%d'),
            'end_date': actual_end_date.strftime('%Y-%m-%d'),
            'years': round(years, 2),
            'start_price': round(start_price, 2),
            'end_price': round(end_price_hfq, 2),  # 后复权价格用于技术指标
            'total_return_pct': round(total_return * 100, 2),
            'annualized_return_pct': round(annualized_return * 100, 2),
            'volatility_pct': round(volatility * 100, 2),
            'sharpe_ratio': round((annualized_return - 0.03) / volatility, 2) if volatility > 0 else np.nan,
            'max_drawdown_pct': round(max_drawdown * 100, 2),
            'win_rate_pct': round(win_rate * 100, 2),
            'avg_debt_to_asset_5y': round(avg_debt_to_asset * 100, 2) if avg_debt_to_asset is not None else None,
            'avg_roe_5y': round(avg_roe * 100, 2) if avg_roe is not None else None,
            'latest_net_profit': latest_net_profit,
            'latest_net_profit_growth': latest_net_profit_growth,
            'latest_price': round(latest_real_price, 2)  # 前复权价格作为真实最新股价
        }

    except Exception as e:
        print(f"处理股票 {ts_code} ({name}) 时出错: {str(e)}")
        return None


def export_results_to_excel(results, filename):
    """
    将结果导出到Excel文件
    包含高收益股票清单和统计摘要
    """
    if results.empty:
        print("没有数据可导出")
        return
    
    # 创建中文列名映射
    chinese_column_names = {
        'ts_code': '股票代码',
        'name': '股票名称',
        'start_date': '起始日期',
        'end_date': '结束日期',
        'years': '年数',
        'start_price': '起始价格',
        'end_price': '结束价格',
        'total_return_pct': '总收益率%',
        'annualized_return_pct': '年化收益率%',
        'volatility_pct': '波动率%',
        'sharpe_ratio': '夏普比率',
        'max_drawdown_pct': '最大回撤%',
        'win_rate_pct': '胜率%',
        'avg_debt_to_asset_5y': '近5年平均资产负债率%',
        'avg_roe_5y': '近5年平均ROE%',
        'latest_net_profit': '最新净利润',
        'latest_net_profit_growth': '最新净利润同比增速%',
        'latest_price': '最新股价'
    }
    
    # 复制结果数据框以避免修改原始数据
    results_chinese = results.rename(columns=chinese_column_names)
    
    # 筛选年化收益率≥12%的股票（放宽条件以获得更丰富的结果）
    high_return_stocks = results_chinese[results_chinese['年化收益率%'] >= 15]
    
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        # 高收益股票清单
        if not high_return_stocks.empty:
            high_return_stocks.to_excel(writer, sheet_name='年化收益率≥15%股票', index=False)
        else:
            # 创建空的工作表
            pd.DataFrame().to_excel(writer, sheet_name='年化收益率≥15%股票', index=False)
        
        # 全部股票清单
        results_chinese.to_excel(writer, sheet_name='全部分析股票', index=False)

        # 统计摘要
        if not results_chinese.empty:
            # 选择数值型列进行统计
            numeric_cols = ['年化收益率%', '总收益率%', '波动率%', '夏普比率', '最大回撤%', '胜率%', '年数', '近5年平均资产负债率%', '近5年平均ROE%', '最新净利润', '最新净利润同比增速%', '最新股价']
            available_numeric_cols = [col for col in numeric_cols if col in results_chinese.columns]
            
            if available_numeric_cols:
                # 为年化收益率≥12%的股票生成统计摘要（如果存在）
                high_return_subset = high_return_stocks[available_numeric_cols] if not high_return_stocks.empty else pd.DataFrame(columns=available_numeric_cols)
                
                if not high_return_subset.empty:
                    performance_summary = high_return_subset[available_numeric_cols].describe()
                    performance_summary.index = ['计数', '均值', '标准差', '最小值', '25%', '50%', '75%', '最大值']
                    performance_summary.to_excel(writer, sheet_name='高收益股票统计摘要')
                else:
                    # 如果没有高收益股票，仍然创建统计摘要
                    performance_summary = results_chinese[available_numeric_cols].describe()
                    performance_summary.index = ['计数', '均值', '标准差', '最小值', '25%', '50%', '75%', '最大值']
                    performance_summary.to_excel(writer, sheet_name='全部股票统计摘要')
    
    print(f"结果已保存至: {filename}")
    print(f"共找到 {len(high_return_stocks)} 只年化收益率≥15%的股票")


def advanced_analysis_with_threading(stock_limit=200):  # 增加测试股票数量
    """
    使用多线程进行更高效的分析
    """
    # 设置时间范围（过去8年数据）
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=25 * 365)).strftime('%Y%m%d')

    print(f"分析期间: {start_date} 到 {end_date}")
    print("正在获取A股股票列表...")

    # 获取A股股票列表
    try:
        stock_info = ak.stock_info_a_code_name()
        # 限制数量以进行快速测试
        stock_list = stock_info.head(20000)  # 分析前200只股票
        print(f"获取到 {len(stock_list)} 只股票信息，开始分析...")
    except Exception as e:
        print(f"获取股票列表失败: {e}")
        return pd.DataFrame()

    results = []
    
    # 使用线程池处理股票数据
    with ThreadPoolExecutor(max_workers=10) as executor:  # 适中的并发数
        # 提交任务
        future_to_stock = {
            executor.submit(get_single_stock_performance, row['code'], row['name'], start_date, end_date): (
            row['code'], row['name'])
            for index, row in stock_list.iterrows()
        }
        
        # 收集结果
        completed = 0
        successful = 0
        for future in as_completed(future_to_stock):
            result = future.result()
            if result:
                results.append(result)
                successful += 1
            
            completed += 1
            if completed % 100 == 0 or completed == len(stock_list):
                print(f"进度: 已完成 {completed}/{len(stock_list)} 只股票的处理，成功 {successful} 只")

    # 创建结果DataFrame
    result_df = pd.DataFrame(results)

    # 筛选年化收益率大于等于15%的股票（放宽条件）
    high_performers = result_df[result_df['annualized_return_pct'] >= 15].sort_values(
        'annualized_return_pct', ascending=False
    ).reset_index(drop=True)

    print(f"\n总共找到 {len(high_performers)} 只年化收益率≥15%的股票")

    return high_performers, result_df


def main(test_mode=True):  # 添加测试模式参数
    """
    主函数
    """
    print("="*60)
    print("A股市场复合年化收益率超过15%的股票分析工具")
    print("分析指标包括：年化收益率、总收益率、波动率、夏普比率、最大回撤、胜率等")
    print("="*60)

    try:
        # 执行分析
        print("\n开始分析...")
        # 在测试模式下，分析更多股票以增加找到高收益股票的机会
        stock_limit = 200 if test_mode else 5000
        results, all_results_df = advanced_analysis_with_threading(stock_limit=stock_limit)

        if results.empty:
            print("\n未找到年化收益率≥15%的股票")
        else:
            print(f"\n找到 {len(results)} 只年化收益率≥15%的股票")

        # 生成输出文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f"A股年化收益率超15%股票_{timestamp}.xlsx"

        # 导出结果
        export_results_to_excel(all_results_df, output_filename)

        # 显示统计信息
        high_results_df = all_results_df[all_results_df['annualized_return_pct'] >= 12].sort_values(
            'annualized_return_pct', ascending=False
        ).reset_index(drop=True)
        
        print(f"\n分析完成！共找到 {len(high_results_df)} 只年化收益率≥12%的股票")

        if len(high_results_df) > 0:
            print("\n前10名高收益股票详情:")
            display_cols = [
                'ts_code', 'name', 'annualized_return_pct', 
                'total_return_pct', 'years', 'volatility_pct', 
                'sharpe_ratio', 'max_drawdown_pct', 'win_rate_pct',
                'avg_debt_to_asset_5y', 'avg_roe_5y', 'latest_net_profit', 'latest_net_profit_growth',
                'latest_price'
            ]
            print(high_results_df[display_cols].head(10).to_string(index=False))
            
            print(f"\n年化收益率分布情况:")
            print(f"最高年化收益率: {high_results_df['annualized_return_pct'].max():.2f}%")
            print(f"最低年化收益率: {high_results_df['annualized_return_pct'].min():.2f}%")
            print(f"平均年化收益率: {high_results_df['annualized_return_pct'].mean():.2f}%")
            print(f"收益率中位数: {high_results_df['annualized_return_pct'].median():.2f}%")
            
            # 输出财务指标统计
            if 'avg_debt_to_asset_5y' in high_results_df.columns and high_results_df['avg_debt_to_asset_5y'].notna().any():
                print(f"平均资产负债率: {high_results_df['avg_debt_to_asset_5y'].mean():.2f}%")
            if 'avg_roe_5y' in high_results_df.columns and high_results_df['avg_roe_5y'].notna().any():
                print(f"平均ROE: {high_results_df['avg_roe_5y'].mean():.2f}%")
            if 'latest_net_profit' in high_results_df.columns and high_results_df['latest_net_profit'].notna().any():
                print(f"平均净利润: {high_results_df['latest_net_profit'].mean():.2f}")
            if 'latest_net_profit_growth' in high_results_df.columns and high_results_df['latest_net_profit_growth'].notna().any():
                print(f"平均净利润同比增速: {high_results_df['latest_net_profit_growth'].mean():.2f}%")
            if 'latest_price' in high_results_df.columns and high_results_df['latest_price'].notna().any():
                print(f"平均最新股价: {high_results_df['latest_price'].mean():.2f}")
        else:
            print("\n在当前分析的股票中未找到年化收益率≥12%的股票")
            if len(all_results_df) > 0:
                print(f"全部分析股票中的最高年化收益率: {all_results_df['annualized_return_pct'].max():.2f}%")
                print(f"全部分析股票中的平均年化收益率: {all_results_df['annualized_return_pct'].mean():.2f}%")

    except Exception as e:
        print(f"执行过程中出现错误: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 运行测试模式
    main(test_mode=True)