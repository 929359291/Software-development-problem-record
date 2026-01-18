import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

warnings.filterwarnings('ignore')

def get_single_stock_performance(ts_code, name, start_date, end_date):
    """
    获取单个股票的性能数据
    """
    try:
        # 获取股票历史数据（前复权）
        df = ak.stock_zh_a_hist(symbol=ts_code, period="daily", start_date=start_date, end_date=end_date, adjust="hfq")

        if df.empty or len(df) < 250:  # 至少需要一年的日线数据
            return None

        df = df.sort_values('日期').reset_index(drop=True)

        # 获取起始和结束价格
        start_price = df.iloc[0]['收盘']
        end_price = df.iloc[-1]['收盘']

        if start_price <= 0:
            return None

        # 计算时间跨度
        actual_start_date = pd.to_datetime(df.iloc[0]['日期'])
        actual_end_date = pd.to_datetime(df.iloc[-1]['日期'])
        years = (actual_end_date - actual_start_date).days / 365.25

        if years < 8:  # 至少需要8年完整数据，以确保数据可靠性
            return None

        # 计算各种指标
        total_return = (end_price - start_price) / start_price
        annualized_return = (end_price / start_price) ** (1 / years) - 1

        # 计算波动率
        df['daily_return'] = df['收盘'].pct_change()
        volatility = df['daily_return'].std() * np.sqrt(244)  # 年化波动率

        # 获取最近5年的财务数据
        avg_debt_to_asset = None
        avg_roe = None
        
        # 初始化指定年份的净利润和同比增长率
        net_profit_2022 = None
        net_profit_2023 = None
        net_profit_2024 = None
        net_profit_growth_2023 = None
        net_profit_growth_2024 = None
        
        try:
            # 尝试获取同花顺财务指标
            try:
                fina_indicator_df = ak.stock_financial_abstract_ths(symbol=ts_code)
                if fina_indicator_df is not None and hasattr(fina_indicator_df, 'empty') and not fina_indicator_df.empty and len(fina_indicator_df) > 0:
                    # 按报告期排序
                    fina_indicator_df = fina_indicator_df.sort_values('报告期').reset_index(drop=True)
                    
                    # 获取最近5年的资产负债率和净资产收益率
                    recent_years_data_5 = fina_indicator_df.tail(5)  # 获取最近5年的数据
                    
                    debt_to_asset_list = []
                    roe_list = []
                    
                    for idx, row in recent_years_data_5.iterrows():
                        # 获取资产负债率
                        debt_to_asset_val = row.get('资产负债率')
                        if debt_to_asset_val is not None and pd.notna(debt_to_asset_val) and debt_to_asset_val != '-' and debt_to_asset_val != '':
                            try:
                                # 去掉百分号并转换为数值
                                val_str = str(debt_to_asset_val).strip()
                                if val_str.endswith('%'):
                                    val = float(val_str.replace('%', '')) / 100
                                elif isinstance(debt_to_asset_val, str) and debt_to_asset_val.endswith('%'):
                                    val = float(debt_to_asset_val.replace('%', '')) / 100
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
                                elif isinstance(roe_val, str) and roe_val.endswith('%'):
                                    val = float(roe_val.replace('%', '')) / 100
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
                    
                    # 遍历所有数据行，查找特定年份的净利润数据
                    for idx, row in fina_indicator_df.iterrows():
                        report_date = str(row.get('报告期', ''))
                        year = report_date.split('-')[0] if '-' in report_date and report_date != 'None' else ''
                        
                        # 根据年份设置净利润值
                        if year == '2022':
                            # 尝试获取净利润（可能的列名）
                            for col_name in ['净利润', '净利润-净利润', '归属母公司股东的净利润']:
                                if col_name in row.index and row[col_name] is not None:
                                    net_profit_val = row[col_name]
                                    if pd.notna(net_profit_val) and net_profit_val != '-' and net_profit_val != '':
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
                                                    net_profit_2022 = float(val_str) * multiplier
                                                except ValueError:
                                                    net_profit_2022 = None
                                            else:
                                                net_profit_2022 = float(val_str)
                                            break
                                        except (ValueError, TypeError):
                                            continue
                        
                        elif year == '2023':
                            # 尝试获取净利润
                            for col_name in ['净利润', '净利润-净利润', '归属母公司股东的净利润']:
                                if col_name in row.index and row[col_name] is not None:
                                    net_profit_val = row[col_name]
                                    if pd.notna(net_profit_val) and net_profit_val != '-' and net_profit_val != '':
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
                                                    net_profit_2023 = float(val_str) * multiplier
                                                except ValueError:
                                                    net_profit_2023 = None
                                            else:
                                                net_profit_2023 = float(val_str)
                                            break
                                        except (ValueError, TypeError):
                                            continue
                            
                            # 尝试获取净利润同比增长率
                            for col_name in ['净利润同比增长率', '净利润-同比增长率', '归属母公司股东的净利润同比增长率']:
                                if col_name in row.index and row[col_name] is not None:
                                    growth_val = row[col_name]
                                    if pd.notna(growth_val) and growth_val != '-' and growth_val != '':
                                        try:
                                            val_str = str(growth_val).strip()
                                            if val_str.endswith('%'):
                                                net_profit_growth_2023 = float(val_str.replace('%', ''))
                                            else:
                                                net_profit_growth_2023 = float(val_str)
                                            break
                                        except (ValueError, TypeError):
                                            continue
                        
                        elif year == '2024':
                            # 尝试获取净利润
                            for col_name in ['净利润', '净利润-净利润', '归属母公司股东的净利润']:
                                if col_name in row.index and row[col_name] is not None:
                                    net_profit_val = row[col_name]
                                    if pd.notna(net_profit_val) and net_profit_val != '-' and net_profit_val != '':
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
                                                    net_profit_2024 = float(val_str) * multiplier
                                                except ValueError:
                                                    net_profit_2024 = None
                                            else:
                                                net_profit_2024 = float(val_str)
                                            break
                                        except (ValueError, TypeError):
                                            continue
                            
                            # 尝试获取净利润同比增长率
                            for col_name in ['净利润同比增长率', '净利润-同比增长率', '归属母公司股东的净利润同比增长率']:
                                if col_name in row.index and row[col_name] is not None:
                                    growth_val = row[col_name]
                                    if pd.notna(growth_val) and growth_val != '-' and growth_val != '':
                                        try:
                                            val_str = str(growth_val).strip()
                                            if val_str.endswith('%'):
                                                net_profit_growth_2024 = float(val_str.replace('%', ''))
                                            else:
                                                net_profit_growth_2024 = float(val_str)
                                            break
                                        except (ValueError, TypeError):
                                            continue
            except Exception as e:
                print(f"同花顺接口错误 {ts_code}: {str(e)}")
                pass
            
            # 如果上述方法获取的数据不足，尝试使用其他接口
            if (avg_debt_to_asset is None or avg_roe is None) and (avg_debt_to_asset != 0 and avg_roe != 0):
                try:
                    # 尝试东方财富财务分析指标
                    em_fina_df = ak.stock_financial_analysis_indicator_em(symbol=ts_code)
                    if em_fina_df is not None and hasattr(em_fina_df, 'empty') and not em_fina_df.empty and len(em_fina_df) > 0:
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
                        
                        # 遍历所有数据行，查找特定年份的净利润数据
                        for idx, row in em_fina_df.iterrows():
                            report_date = str(row.get('报告期', ''))
                            year = report_date.split('-')[0] if '-' in report_date and report_date != 'None' else ''
                            
                            # 根据年份设置净利润值
                            if year == '2022' and net_profit_2022 is None:
                                # 尝试获取净利润
                                for col_name in ['净利润', '净利润-净利润', '归属母公司股东的净利润']:
                                    if col_name in row.index and row[col_name] is not None:
                                        net_profit_val = row[col_name]
                                        if pd.notna(net_profit_val) and net_profit_val != '-' and net_profit_val != '':
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
                                                        net_profit_2022 = float(val_str) * multiplier
                                                    except ValueError:
                                                        net_profit_2022 = None
                                                else:
                                                    net_profit_2022 = float(val_str)
                                                break
                                            except (ValueError, TypeError):
                                                continue
                            
                            elif year == '2023' and net_profit_2023 is None:
                                # 尝试获取净利润
                                for col_name in ['净利润', '净利润-净利润', '归属母公司股东的净利润']:
                                    if col_name in row.index and row[col_name] is not None:
                                        net_profit_val = row[col_name]
                                        if pd.notna(net_profit_val) and net_profit_val != '-' and net_profit_val != '':
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
                                                        net_profit_2023 = float(val_str) * multiplier
                                                    except ValueError:
                                                        net_profit_2023 = None
                                                else:
                                                    net_profit_2023 = float(val_str)
                                                break
                                            except (ValueError, TypeError):
                                                continue
                                
                                # 尝试获取净利润同比增长率
                                if net_profit_growth_2023 is None:
                                    for col_name in ['净利润同比增长率', '净利润-同比增长率', '归属母公司股东的净利润同比增长率']:
                                        if col_name in row.index and row[col_name] is not None:
                                            growth_val = row[col_name]
                                            if pd.notna(growth_val) and growth_val != '-' and growth_val != '':
                                                try:
                                                    val_str = str(growth_val).strip()
                                                    if val_str.endswith('%'):
                                                        net_profit_growth_2023 = float(val_str.replace('%', ''))
                                                    else:
                                                        net_profit_growth_2023 = float(val_str)
                                                    break
                                                except (ValueError, TypeError):
                                                    continue
                            
                            elif year == '2024' and net_profit_2024 is None:
                                # 尝试获取净利润
                                for col_name in ['净利润', '净利润-净利润', '归属母公司股东的净利润']:
                                    if col_name in row.index and row[col_name] is not None:
                                        net_profit_val = row[col_name]
                                        if pd.notna(net_profit_val) and net_profit_val != '-' and net_profit_val != '':
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
                                                        net_profit_2024 = float(val_str) * multiplier
                                                    except ValueError:
                                                        net_profit_2024 = None
                                                else:
                                                    net_profit_2024 = float(val_str)
                                                break
                                            except (ValueError, TypeError):
                                                continue
                                
                                # 尝试获取净利润同比增长率
                                if net_profit_growth_2024 is None:
                                    for col_name in ['净利润同比增长率', '净利润-同比增长率', '归属母公司股东的净利润同比增长率']:
                                        if col_name in row.index and row[col_name] is not None:
                                            growth_val = row[col_name]
                                            if pd.notna(growth_val) and growth_val != '-' and growth_val != '':
                                                try:
                                                    val_str = str(growth_val).strip()
                                                    if val_str.endswith('%'):
                                                        net_profit_growth_2024 = float(val_str.replace('%', ''))
                                                    else:
                                                        net_profit_growth_2024 = float(val_str)
                                                    break
                                                except (ValueError, TypeError):
                                                    continue
                except Exception as e:
                    print(f"东方财富接口错误 {ts_code}: {str(e)}")
                    pass
            
            # 如果仍有数据缺失，尝试第三个数据源 - 使用akshare的另一个财务接口
            if (avg_debt_to_asset is None or avg_roe is None) and (avg_debt_to_asset != 0 and avg_roe != 0):
                try:
                    # 尝试使用ak.stock_financial_abstract接口获取财务指标
                    fina_main_df = ak.stock_financial_abstract(symbol=ts_code)
                    if fina_main_df is not None and hasattr(fina_main_df, 'empty') and not fina_main_df.empty and len(fina_main_df) > 0:
                        # 按报告期排序
                        fina_main_df = fina_main_df.sort_values('报告期').reset_index(drop=True)
                        
                        recent_main_data = fina_main_df.tail(5)  # 获取最近5年的数据
                        
                        main_debt_to_asset_list = []
                        main_roe_list = []
                        
                        for idx, row in recent_main_data.iterrows():
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
                                        main_debt_to_asset_list.append(val)
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
                                        main_roe_list.append(val)
                                    except (ValueError, AttributeError):
                                        pass
                        
                        if avg_debt_to_asset is None and main_debt_to_asset_list:
                            avg_debt_to_asset = np.mean(main_debt_to_asset_list)
                        if avg_roe is None and main_roe_list:
                            avg_roe = np.mean(main_roe_list)
                        
                        # 遍历所有数据行，查找特定年份的净利润数据
                        for idx, row in fina_main_df.iterrows():
                            report_date = str(row.get('报告期', ''))
                            year = report_date.split('-')[0] if '-' in report_date and report_date != 'None' else ''
                            
                            # 根据年份设置净利润值
                            if year == '2022' and net_profit_2022 is None:
                                # 尝试获取净利润
                                for col_name in ['净利润', '净利润-净利润', '归属母公司股东的净利润']:
                                    if col_name in row.index and row[col_name] is not None:
                                        net_profit_val = row[col_name]
                                        if pd.notna(net_profit_val) and net_profit_val != '-' and net_profit_val != '':
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
                                                        net_profit_2022 = float(val_str) * multiplier
                                                    except ValueError:
                                                        net_profit_2022 = None
                                                else:
                                                    net_profit_2022 = float(val_str)
                                                break
                                            except (ValueError, TypeError):
                                                continue
                            
                            elif year == '2023' and net_profit_2023 is None:
                                # 尝试获取净利润
                                for col_name in ['净利润', '净利润-净利润', '归属母公司股东的净利润']:
                                    if col_name in row.index and row[col_name] is not None:
                                        net_profit_val = row[col_name]
                                        if pd.notna(net_profit_val) and net_profit_val != '-' and net_profit_val != '':
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
                                                        net_profit_2023 = float(val_str) * multiplier
                                                    except ValueError:
                                                        net_profit_2023 = None
                                                else:
                                                    net_profit_2023 = float(val_str)
                                                break
                                            except (ValueError, TypeError):
                                                continue
                                
                                # 尝试获取净利润同比增长率
                                if net_profit_growth_2023 is None:
                                    for col_name in ['净利润同比增长率', '净利润-同比增长率', '归属母公司股东的净利润同比增长率']:
                                        if col_name in row.index and row[col_name] is not None:
                                            growth_val = row[col_name]
                                            if pd.notna(growth_val) and growth_val != '-' and growth_val != '':
                                                try:
                                                    val_str = str(growth_val).strip()
                                                    if val_str.endswith('%'):
                                                        net_profit_growth_2023 = float(val_str.replace('%', ''))
                                                    else:
                                                        net_profit_growth_2023 = float(val_str)
                                                    break
                                                except (ValueError, TypeError):
                                                    continue
                            
                            elif year == '2024' and net_profit_2024 is None:
                                # 尝试获取净利润
                                for col_name in ['净利润', '净利润-净利润', '归属母公司股东的净利润']:
                                    if col_name in row.index and row[col_name] is not None:
                                        net_profit_val = row[col_name]
                                        if pd.notna(net_profit_val) and net_profit_val != '-' and net_profit_val != '':
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
                                                        net_profit_2024 = float(val_str) * multiplier
                                                    except ValueError:
                                                        net_profit_2024 = None
                                                else:
                                                    net_profit_2024 = float(val_str)
                                                break
                                            except (ValueError, TypeError):
                                                continue
                                
                                # 尝试获取净利润同比增长率
                                if net_profit_growth_2024 is None:
                                    for col_name in ['净利润同比增长率', '净利润-同比增长率', '归属母公司股东的净利润同比增长率']:
                                        if col_name in row.index and row[col_name] is not None:
                                            growth_val = row[col_name]
                                            if pd.notna(growth_val) and growth_val != '-' and growth_val != '':
                                                try:
                                                    val_str = str(growth_val).strip()
                                                    if val_str.endswith('%'):
                                                        net_profit_growth_2024 = float(val_str.replace('%', ''))
                                                    else:
                                                        net_profit_growth_2024 = float(val_str)
                                                    break
                                                except (ValueError, TypeError):
                                                    continue
                except Exception as e:
                    print(f"第三数据源接口错误 {ts_code}: {str(e)}")
                    pass
            
            # 如果仍有数据缺失，尝试第四个数据源 - 使用业绩报告接口
            if (avg_debt_to_asset is None or avg_roe is None) and (avg_debt_to_asset != 0 and avg_roe != 0):
                try:
                    # 尝试使用ak.stock_yjbb_em接口获取业绩报告
                    yjbb_df = ak.stock_yjbb_em(symbol=ts_code)
                    if yjbb_df is not None and hasattr(yjbb_df, 'empty') and not yjbb_df.empty and len(yjbb_df) > 0:
                        # 按报告期排序
                        yjbb_df = yjbb_df.sort_values('报告期').reset_index(drop=True)
                        
                        # 遍历所有数据行，查找特定年份的净利润数据和其他指标
                        for idx, row in yjbb_df.iterrows():
                            report_date = str(row.get('报告期', ''))
                            year = report_date.split('-')[0] if '-' in report_date and report_date != 'None' else ''
                            
                            # 根据年份设置净利润值
                            if year == '2022' and net_profit_2022 is None:
                                # 尝试获取净利润
                                for col_name in ['净利润', '扣非净利润', '营业总收入']:
                                    if col_name in row.index and row[col_name] is not None:
                                        net_profit_val = row[col_name]
                                        if pd.notna(net_profit_val) and net_profit_val != '-' and net_profit_val != '':
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
                                                        net_profit_2022 = float(val_str) * multiplier
                                                    except ValueError:
                                                        net_profit_2022 = None
                                                else:
                                                    net_profit_2022 = float(val_str)
                                                break
                                            except (ValueError, TypeError):
                                                continue
                            
                            elif year == '2023' and net_profit_2023 is None:
                                # 尝试获取净利润
                                for col_name in ['净利润', '扣非净利润', '营业总收入']:
                                    if col_name in row.index and row[col_name] is not None:
                                        net_profit_val = row[col_name]
                                        if pd.notna(net_profit_val) and net_profit_val != '-' and net_profit_val != '':
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
                                                        net_profit_2023 = float(val_str) * multiplier
                                                    except ValueError:
                                                        net_profit_2023 = None
                                                else:
                                                    net_profit_2023 = float(val_str)
                                                break
                                            except (ValueError, TypeError):
                                                continue
                                
                                # 尝试获取净利润同比增长率
                                if net_profit_growth_2023 is None:
                                    for col_name in ['净利润同比增长率', '同比增长率', '营业总收入同比增长率']:
                                        if col_name in row.index and row[col_name] is not None:
                                            growth_val = row[col_name]
                                            if pd.notna(growth_val) and growth_val != '-' and growth_val != '':
                                                try:
                                                    val_str = str(growth_val).strip()
                                                    if val_str.endswith('%'):
                                                        net_profit_growth_2023 = float(val_str.replace('%', ''))
                                                    else:
                                                        net_profit_growth_2023 = float(val_str)
                                                    break
                                                except (ValueError, TypeError):
                                                    continue
                            
                            elif year == '2024' and net_profit_2024 is None:
                                # 尝试获取净利润
                                for col_name in ['净利润', '扣非净利润', '营业总收入']:
                                    if col_name in row.index and row[col_name] is not None:
                                        net_profit_val = row[col_name]
                                        if pd.notna(net_profit_val) and net_profit_val != '-' and net_profit_val != '':
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
                                                        net_profit_2024 = float(val_str) * multiplier
                                                    except ValueError:
                                                        net_profit_2024 = None
                                                else:
                                                    net_profit_2024 = float(val_str)
                                                break
                                            except (ValueError, TypeError):
                                                continue
                                
                                # 尝试获取净利润同比增长率
                                if net_profit_growth_2024 is None:
                                    for col_name in ['净利润同比增长率', '同比增长率', '营业总收入同比增长率']:
                                        if col_name in row.index and row[col_name] is not None:
                                            growth_val = row[col_name]
                                            if pd.notna(growth_val) and growth_val != '-' and growth_val != '':
                                                try:
                                                    val_str = str(growth_val).strip()
                                                    if val_str.endswith('%'):
                                                        net_profit_growth_2024 = float(val_str.replace('%', ''))
                                                    else:
                                                        net_profit_growth_2024 = float(val_str)
                                                    break
                                                except (ValueError, TypeError):
                                                    continue
                except Exception as e:
                    print(f"第四数据源接口错误 {ts_code}: {str(e)}")
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
            'end_price': round(end_price, 2),
            'total_return_pct': round(total_return * 100, 2),
            'annualized_return_pct': round(annualized_return * 100, 2),
            'volatility_pct': round(volatility * 100, 2),
            'sharpe_ratio': round((annualized_return - 0.03) / volatility, 2) if volatility > 0 else np.nan,
            'avg_debt_to_asset_5y': round(avg_debt_to_asset * 100, 2) if avg_debt_to_asset is not None else None,
            'avg_roe_5y': round(avg_roe * 100, 2) if avg_roe is not None else None,
            'net_profit_2022': net_profit_2022,
            'net_profit_2023': net_profit_2023,
            'net_profit_2024': net_profit_2024,
            'net_profit_growth_2023': net_profit_growth_2023,
            'net_profit_growth_2024': net_profit_growth_2024
        }

    except Exception as e:
        print(f"处理股票 {ts_code} ({name}) 时出错: {str(e)}")
        return None


def export_results_to_excel(results, filename):
    """
    将结果导出到Excel文件
    """
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
        'avg_debt_to_asset_5y': '近5年平均资产负债率%',
        'avg_roe_5y': '近5年平均ROE%',
        'net_profit_2022': '2022年净利润',
        'net_profit_2023': '2023年净利润',
        'net_profit_2024': '2024年净利润',
        'net_profit_growth_2023': '2023年净利润同比增速%',
        'net_profit_growth_2024': '2024年净利润同比增速%'
    }
    
    # 复制结果数据框以避免修改原始数据
    results_chinese = results.rename(columns=chinese_column_names)
    
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        # 主要结果表 - 只导出年化收益率≥15%的股票
        high_return_stocks = results_chinese[results_chinese['年化收益率%'] >= 15]
        high_return_stocks.to_excel(writer, sheet_name='高收益股票', index=False)

        # 按年化收益率排序统计
        if not results.empty:
            # 为统计摘要选择有意义的数值列
            numeric_cols = ['年化收益率%', '总收益率%', '波动率%', '夏普比率', '近5年平均资产负债率%', '近5年平均ROE%']
            # 检查财务数据列是否存在于数据框中
            financial_cols = ['2022年净利润', '2023年净利润', '2024年净利润', '2023年净利润同比增速%', '2024年净利润同比增速%']
            available_numeric_cols = [col for col in numeric_cols if col in results_chinese.columns]
            # 添加存在的财务列
            for col in financial_cols:
                if col in results_chinese.columns:
                    available_numeric_cols.append(col)
            
            if available_numeric_cols:
                performance_summary = results_chinese[available_numeric_cols].describe()
                # 重命名索引为中文
                performance_summary.index = ['计数', '均值', '标准差', '最小值', '25%', '50%', '75%', '最大值']
                performance_summary.to_excel(writer, sheet_name='统计摘要')

    print(f"结果已保存至: {filename}")
    print(f"其中包含 {len(high_return_stocks)} 只年化收益率≥15%的股票")


def advanced_analysis_with_threading():
    """
    使用多线程进行更高效的分析
    """
    # 计算时间范围
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=25 * 365)).strftime('%Y%m%d')  # 使用25年而非30年，增加找到符合条件股票的概率

    print(f"开始日期: {start_date}, 结束日期: {end_date}")

    # 获取A股股票列表
    try:
        stock_info = ak.stock_info_a_code_name()
        stock_list = stock_info.head(20000)  # 限制数量以快速测试，可根据需要调整
        print(f"获取到 {len(stock_list)} 只股票信息")
    except Exception as e:
        print(f"获取股票列表失败: {e}")
        return pd.DataFrame()

    results = []
    
    # 使用线程池处理股票数据
    with ThreadPoolExecutor(max_workers=50) as executor:  # 进一步降低并发数以提高稳定性
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
            if completed % 5 == 0 or completed == len(stock_list):
                print(f"已完成 {completed}/{len(stock_list)} 只股票的处理，成功 {successful} 只")

    # 创建结果DataFrame
    result_df = pd.DataFrame(results)

    # 筛选年化收益率大于15%的股票
    high_performers = result_df[result_df['annualized_return_pct'] > 15].sort_values(
        'annualized_return_pct', ascending=False
    ).reset_index(drop=True)

    print(f"\n总共找到 {len(high_performers)} 只年化收益率超过15%的股票")

    return high_performers


def main():
    """
    主函数
    """
    print("开始使用AkShare分析A股市场高收益股票...")

    try:
        # 执行分析
        results = advanced_analysis_with_threading()

        if results.empty:
            print("未找到年化收益率超过15%的股票")
            return

        # 生成输出文件名
        output_filename = f"a_stock_high_performers_akshare_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        # 导出结果
        export_results_to_excel(results, output_filename)

        # 显示统计信息
        print(f"\n分析完成！共找到 {len(results)} 只年化收益率超过15%的股票")

        if len(results) > 0:
            print("\n前10名高收益股票（含新增指标）:")
            # 显示包含新增指标的列
            display_cols = ['ts_code', 'name', 'annualized_return_pct', 'total_return_pct', 'years', 
                           'avg_debt_to_asset_5y', 'avg_roe_5y']
            # 检查并添加存在的财务数据列
            financial_cols = ['2022年净利润', '2023年净利润', '2024年净利润',
                              '2023年净利润同比增速%', '2024年净利润同比增速%']
            for col in financial_cols:
                if col in results.columns:
                    display_cols.append(col)
            if 'industry' in results.columns:
                display_cols.insert(2, 'industry')
            print(results[display_cols].head(10).to_string(index=False))

    except Exception as e:
        print(f"执行过程中出现错误: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
