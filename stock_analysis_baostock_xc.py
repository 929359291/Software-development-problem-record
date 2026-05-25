"""
使用baostock分析A股市场年化收益率超过15%的股票（多进程版本）
该脚本从baostock获取A股数据，计算年化收益率等指标，并输出到Excel文件
"""

import pandas as pd
import numpy as np
import baostock as bs
from datetime import datetime, timedelta
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
import os
import multiprocessing

warnings.filterwarnings('ignore')

# macOS上fork模式会导致子进程继承父进程的锁状态，容易死锁
# 必须使用spawn模式来安全地创建子进程
if __name__ == '__main__':
    multiprocessing.set_start_method('spawn', force=True)


def init_baostock_process():
    """在每个进程中初始化baostock连接"""
    try:
        bs.login()
        print(f"进程 {os.getpid()} 已登录baostock")
        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"进程 {os.getpid()} 登录baostock失败: {str(e)}")
        return False


def safe_float_convert(value):
    """安全转换为浮点数，处理空值和无效值"""
    if value is None or str(value).strip() == '' or pd.isna(value):
        return 0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0


def format_amount(amount):
    """
    将金额数值格式化为合适的单位：万、十万、百万、千万、亿
    """
    if pd.isna(amount) or amount == 0:
        return "0"
    abs_amount = abs(amount)
    if abs_amount >= 1e8:  # 1亿及以上
        return f"{amount / 1e8:.2f}亿"
    elif abs_amount >= 1e7:  # 千万及以上
        return f"{amount / 1e7:.2f}千万"
    elif abs_amount >= 1e6:  # 百万及以上
        return f"{amount / 1e6:.2f}百万"
    elif abs_amount >= 1e5:  # 十万及以上
        return f"{amount / 1e5:.2f}十万"
    elif abs_amount >= 1e4:  # 万及以上
        return f"{amount / 1e4:.2f}万"
    else:  # 少于一万
        return f"{amount:.2f}"


def apply_formatting_to_excel_column(df, amount_column):
    """
    对DataFrame中的金额列应用单位格式化
    """
    df[amount_column + '_formatted'] = df[amount_column].apply(format_amount)
    return df


def get_single_stock_performance_process(args):
    """
    在独立进程中获取单个股票的性能数据
    包括年化收益率、总收益率、波动率、夏普比率等关键指标
    """
    # 解包参数
    ts_code, name, start_date, end_date = args
    pid = str(os.getpid())
    # 每个进程需要单独登录baostock
    login_result = init_baostock_process()
    if not login_result:
        print(f"进程 {os.getpid()} 无法连接到baostock，跳过股票 {ts_code}")
        return None

    try:
        # 使用传入的完整股票代码（已包含交易所前缀）
        bs_code = ts_code

        # 从baostock获取股票历史数据
        rs = bs.query_history_k_data_plus(bs_code,
                                          "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST,peTTM,pbMRQ,psTTM,pcfNcfTTM",
                                          start_date=start_date, end_date=end_date,
                                          frequency="d", adjustflag="1")  # 使用后复权数据

        data_list = []
        while (rs.error_code == '0') & (rs.next()):
            data_list.append(rs.get_row_data())

        if len(data_list) == 0:
            print(f"进程 {os.getpid()}: 未能获取到股票 {ts_code} 的数据")
            return None

        df = pd.DataFrame(data_list, columns=rs.fields)

        if df.empty or len(df) < 250:  # 至少需要一年的日线数据
            return None

        # 确保数值列是数字类型
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df = df.dropna(subset=['close'])
        df = df.sort_values('date').reset_index(drop=True)

        # 获取起始和结束价格
        start_price = safe_float_convert(float(df.iloc[0]['close']))
        end_price = safe_float_convert(float(df.iloc[-1]['close']))
        peTTM = safe_float_convert(float(df.iloc[-1]['peTTM']))
        pbMRQ = safe_float_convert(float(df.iloc[-1]['pbMRQ']))
        psTTM = safe_float_convert(float(df.iloc[-1]['psTTM']))
        pcfNcfTTM = safe_float_convert(float(df.iloc[-1]['pcfNcfTTM']))


        if start_price <= 0:
            return None

        # 计算时间跨度
        actual_start_date = pd.to_datetime(df.iloc[0]['date'])
        actual_end_date = pd.to_datetime(df.iloc[-1]['date'])
        years = (actual_end_date - actual_start_date).days / 365.25

        if years < 5:  # 至少需要2年数据
            return None

        # 计算各种指标
        total_return = (end_price - start_price) / start_price
        annualized_return = (end_price / start_price) ** (1 / years) - 1

        # 计算波动率
        df['daily_return'] = df['close'].pct_change()
        volatility = df['daily_return'].std() * np.sqrt(244)  # 年化波动率

        # 计算夏普比率（假设无风险利率为3%）
        sharpe_ratio = (annualized_return - 0.03) / volatility if volatility > 0 else np.nan

        # 计算最大回撤
        df['cumulative_return'] = (1 + df['daily_return']).cumprod()
        df['rolling_max'] = df['cumulative_return'].expanding().max()
        df['drawdown'] = (df['cumulative_return'] - df['rolling_max']) / df['rolling_max']
        max_drawdown = abs(df['drawdown'].min()) if not df['drawdown'].empty else 0

        # 计算胜率（正收益天数比例）
        positive_returns = len(df[df['daily_return'] > 0])
        total_trading_days = len(df.dropna(subset=['daily_return']))
        win_rate = positive_returns / total_trading_days if total_trading_days > 0 else 0

        # 获取前复权收盘股价
        rs_front = bs.query_history_k_data_plus(bs_code,
                                                "date,code,open,high,low,close,preclose,volume,amount,adjustflag",
                                                start_date=start_date, end_date=end_date,
                                                frequency="d", adjustflag="2")  # 使用后复权数据

        data_list_f = []
        while (rs_front.error_code == '0') & (rs_front.next()):
            data_list_f.append(rs_front.get_row_data())

        if len(data_list_f) == 0:
            front_price = 0
        else:
            df_f = pd.DataFrame(data_list_f, columns=rs_front.fields)
            front_price = safe_float_convert(df_f.iloc[-1]['close'])


        year = 2026
        year_before = 2025
        quarter = 1
        # 成长能力
        growth_list = []
        rs_growth = bs.query_growth_data(code=bs_code, year=year, quarter=quarter)
        while (rs_growth.error_code == '0') & rs_growth.next():
            growth_list.append(rs_growth.get_row_data())
        # YOYEquity	净资产同比增长率,YOYAsset	总资产同比增长率, YOYNI	净利润同比增长率,YOYEPSBasic	基本每股收益同比增长率,YOYPNI	归属母公司股东净利润同比增长率
        if len(growth_list) == 0:
            YOYEquity = 0
            YOYAsset = 0
            YOYNI = 0
            YOYEPSBasic = 0
            YOYPNI = 0
        else:
            result_growth = pd.DataFrame(growth_list, columns=rs_growth.fields)
            YOYEquity = safe_float_convert(result_growth.iloc[-1]['YOYEquity'])
            YOYAsset = safe_float_convert(result_growth.iloc[-1]['YOYAsset'])
            YOYNI = safe_float_convert(result_growth.iloc[-1]['YOYNI'])
            YOYEPSBasic = safe_float_convert(result_growth.iloc[-1]['YOYEPSBasic'])
            YOYPNI = safe_float_convert(result_growth.iloc[-1]['YOYPNI'])

        # 偿债能力
        balance_list = []
        rs_balance = bs.query_balance_data(code=bs_code, year=year, quarter=quarter)
        while (rs_balance.error_code == '0') & rs_balance.next():
            balance_list.append(rs_balance.get_row_data())

        if len(balance_list) == 0:
            currentRatio = 0
            quickRatio = 0
            cashRatio = 0
            YOYLiability = 0
            liabilityToAsset = 0
            assetToEquity = 0
        else:
            result_balance = pd.DataFrame(balance_list, columns=rs_balance.fields)
            currentRatio = safe_float_convert(result_balance.iloc[-1]['currentRatio'])
            quickRatio = safe_float_convert(result_balance.iloc[-1]['quickRatio'])
            cashRatio = safe_float_convert(result_balance.iloc[-1]['cashRatio'])
            YOYLiability = safe_float_convert(result_balance.iloc[-1]['YOYLiability'])
            liabilityToAsset = safe_float_convert(result_balance.iloc[-1]['liabilityToAsset'])
            assetToEquity = safe_float_convert(result_balance.iloc[-1]['assetToEquity'])

        # 营运能力
        operation_list = []
        rs_operation = bs.query_operation_data(code=bs_code, year=year, quarter=quarter)
        while (rs_operation.error_code == '0') & rs_operation.next():
            operation_list.append(rs_operation.get_row_data())

        if len(operation_list) == 0:
            NRTurnRatio = 0
            NRTurnDays = 0
            INVTurnRatio = 0
            INVTurnDays = 0
            CATurnRatio = 0
            AssetTurnRatio = 0
        else:
            result_operation = pd.DataFrame(operation_list, columns=rs_operation.fields)
            NRTurnRatio = safe_float_convert(result_operation.iloc[-1]['NRTurnRatio'])
            NRTurnDays = safe_float_convert(result_operation.iloc[-1]['NRTurnDays'])
            INVTurnRatio = safe_float_convert(result_operation.iloc[-1]['INVTurnRatio'])
            INVTurnDays = safe_float_convert(result_operation.iloc[-1]['INVTurnDays'])
            CATurnRatio = safe_float_convert(result_operation.iloc[-1]['CATurnRatio'])
            AssetTurnRatio = safe_float_convert(result_operation.iloc[-1]['AssetTurnRatio'])

        # 盈利能力
        profit_list = []
        rs_profit = bs.query_profit_data(code=bs_code, year=year, quarter=quarter)
        while (rs_profit.error_code == '0') & rs_profit.next():
            profit_list.append(rs_profit.get_row_data())

        if len(profit_list) == 0:
            roeAvg = 0
            npMargin = 0
            gpMargin = 0
            netProfit = 0
            epsTTM = 0
            MBRevenue = 0
            totalShare = 0
            liqaShare = 0
        else:
            result_profit = pd.DataFrame(profit_list, columns=rs_profit.fields)
            roeAvg = safe_float_convert(result_profit.iloc[-1]['roeAvg'])
            npMargin = safe_float_convert(result_profit.iloc[-1]['npMargin'])
            gpMargin = safe_float_convert(result_profit.iloc[-1]['gpMargin'])
            netProfit = safe_float_convert(result_profit.iloc[-1]['netProfit'])
            epsTTM = safe_float_convert(result_profit.iloc[-1]['epsTTM'])
            MBRevenue = safe_float_convert(result_profit.iloc[-1]['MBRevenue'])
            totalShare = safe_float_convert(result_profit.iloc[-1]['totalShare'])
            liqaShare = safe_float_convert(result_profit.iloc[-1]['liqaShare'])

        ## 每股分红
        rs_list = []
        rs_dividend = bs.query_dividend_data(code=bs_code, year=year_before, yearType="report")
        while (rs_dividend.error_code == '0') & rs_dividend.next():
            rs_list.append(rs_dividend.get_row_data())
        if len(rs_list) == 0:
            dividCashPsBeforeTax = 0

        else:
            result_dividend = pd.DataFrame(rs_list, columns=rs_dividend.fields)
            dividCashPsBeforeTax = safe_float_convert(result_dividend['dividCashPsBeforeTax'].astype(float, errors='ignore').sum())


        result = {
            'ts_code': ts_code,
            'name': name,
            'start_date': actual_start_date.strftime('%Y-%m-%d'),
            'end_date': actual_end_date.strftime('%Y-%m-%d'),
            'years': round(years, 2),
            'start_price': round(start_price, 2),
            'end_price': round(end_price, 2),
            'front_price': round(front_price, 2),
            'total_return_pct': round(total_return * 100, 2),
            'annualized_return_pct': round(annualized_return * 100, 2),
            'dividend': round(dividCashPsBeforeTax / front_price if front_price != 0 else 1, 4),
            'volatility_pct': round(volatility * 100, 2),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'max_drawdown_pct': round(max_drawdown * 100, 2),
            'win_rate_pct': round(win_rate * 100, 2),
            'peTTM': round(peTTM, 2),
            'pbMRQ': round(pbMRQ, 2),
            'psTTM': round(psTTM, 2),
            'pcfNcfTTM': round(pcfNcfTTM, 2),
            'YOYEquity': round(YOYEquity * 100, 2),
            'YOYAsset': round(YOYAsset * 100, 2),
            'YOYNI': round(YOYNI * 100, 2),
            'YOYEPSBasic': round(YOYEPSBasic * 100, 2),
            'YOYPNI': round(YOYPNI * 100, 2),
            'currentRatio': round(currentRatio * 100, 2),
            'quickRatio': round(quickRatio * 100, 2),
            'cashRatio': round(cashRatio * 100, 2),
            'YOYLiability': round(YOYLiability * 100, 2),
            'liabilityToAsset': round(liabilityToAsset * 100, 2),
            'assetToEquity': round(assetToEquity, 2),
            'NRTurnRatio': round(NRTurnRatio * 100, 2),
            'NRTurnDays': round(NRTurnDays, 2),
            'INVTurnRatio': round(INVTurnRatio * 100, 2),
            'INVTurnDays': round(INVTurnDays, 2),
            'CATurnRatio': round(CATurnRatio * 100, 2),
            'AssetTurnRatio': round(AssetTurnRatio * 100, 2),
            'roeAvg': round(roeAvg * 100, 2),
            'npMargin': round(npMargin * 100, 2),
            'gpMargin': round(gpMargin * 100, 2),
            'netProfit': round(netProfit, 2),
            'epsTTM': round(epsTTM, 2),
            'MBRevenue': round(MBRevenue, 2),
            'totalShare': round(totalShare, 2),
            'liqaShare': round(liqaShare, 2),
            'dividCashPsBeforeTax': round(dividCashPsBeforeTax, 2)
        }
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"进程 {os.getpid()}: 处理股票 {ts_code} ({name}) 时出错: {str(e)}")
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
        'front_price': '前复权价格',
        'total_return_pct': '总收益率%',
        'annualized_return_pct': '年化收益率%',
        'dividend': '股息率',
        'liabilityToAsset': '资产负债率',
        'roeAvg': '净资产收益率[盈利能力]',
        'npMargin': '销售净利率',
        'gpMargin': '销售毛利率',
        'netProfit': '净利润',
        'peTTM': '滚动市盈率',
        'pbMRQ': '市净率',
        'psTTM': '滚动市销率',
        'YOYEquity': '净资产同比增长率[成长能力]',
        'YOYAsset': '总资产同比增长率',
        'YOYNI': '净利润同比增长率',
        'YOYLiability': '总负债同比增长率',
        'volatility_pct': '波动率%',
        'sharpe_ratio': '夏普比率',
        'max_drawdown_pct': '最大回撤%',
        'win_rate_pct': '胜率%',
        'pcfNcfTTM': '滚动市现率',
        'YOYEPSBasic': '基本每股收益同比增长率',
        'YOYPNI': '归属母公司股东净利润同比增长率',
        'currentRatio': '流动比率[偿债能力]',
        'quickRatio': '速动比率',
        'cashRatio': '现金比率',
        'assetToEquity': '权益乘数',
        'NRTurnRatio': '应收账款周转率(次)[运营能力]',
        'NRTurnDays': '应收账款周转天数(天)',
        'INVTurnRatio': '存货周转率(次)',
        'INVTurnDays': '存货周转天数(天)',
        'CATurnRatio': '流动资产周转率(次)',
        'AssetTurnRatio': '总资产周转率',
        'epsTTM': '每股收益',
        'MBRevenue': '主营业务收入',
        'totalShare': '总股本',
        'liqaShare': '流通股本',
        'dividCashPsBeforeTax': '每股分红税前'
    }

    # 复制结果数据框以避免修改原始数据
    results_chinese = results.rename(columns=chinese_column_names)
    results_chinese = apply_formatting_to_excel_column(results_chinese, '净利润')
    results_chinese = apply_formatting_to_excel_column(results_chinese, '主营业务收入')

    # 筛选年化收益率≥15%的股票
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
            numeric_cols = ['年化收益率%', '总收益率%', '波动率%', '夏普比率', '最大回撤%', '胜率%', '年数']
            available_numeric_cols = [col for col in numeric_cols if col in results_chinese.columns]

            if available_numeric_cols:
                # 为年化收益率≥15%的股票生成统计摘要（如果存在）
                high_return_subset = high_return_stocks[
                    available_numeric_cols] if not high_return_stocks.empty else pd.DataFrame(
                    columns=available_numeric_cols)

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

def get_a_excel_list():
    df = pd.read_excel("样本整理.xlsx")
    df = df.drop_duplicates(subset=['股票代码'])
    result = df[['股票代码', '股票名称']].rename(columns={'股票代码': 'code', '股票名称': 'code_name'})
    # 返回前100只股票作为示例
    sample_stocks = result.head(10000)[['code', 'code_name']].rename(columns={'code_name': 'name'})
    return sample_stocks

def get_a_share_list():
    """
    获取A股股票列表
    从baostock获取A股列表
    """
    try:
        # 登录baostock
        lg = bs.login()

        # 获取沪深A股信息
        rs = bs.query_stock_basic()  # 不使用日期和类型参数

        data_list = []
        while (rs.error_code == '0') & (rs.next()):
            data_list.append(rs.get_row_data())

        result = pd.DataFrame(data_list, columns=rs.fields)
        print(rs.fields)

        # 选择部分重点股票进行分析（因为全部分析会很耗时）
        # 过滤掉ST股票
        result = result[result['code_name'].str.contains('ST') == False]
        #保持股票代码完整格式（包含sh./sz.前缀），因为baostock的API需要完整代码
        #不移除交易所前缀，直接使用完整的股票代码
        #登出baostock
        sample_stocks = result.head(10000)[['code', 'code_name']].rename(columns={'code_name': 'name'})

        bs.logout()

        return sample_stocks

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"获取股票列表失败: {str(e)}")
        # 如果baostock获取失败，返回一个样本列表
        # 注意：需要添加交易所前缀以符合baostock API要求
        sample_stocks = [
            {'code': 'sz.000002', 'name': '万科A'},
            {'code': 'sz.002594', 'name': '比亚迪'},
            {'code': 'sh.600036', 'name': '招商银行'},

        ]

        return pd.DataFrame(sample_stocks)


def advanced_analysis_with_multiprocessing(stock_limit=50):  # 限制股票数量以避免过多的网络请求
    """
    使用多进程进行更高效的分析
    """
    # 设置时间范围（过去10年数据）
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=35 * 365)).strftime('%Y-%m-%d')

    print(f"分析期间: {start_date} 到 {end_date}")
    print("正在获取A股股票列表...")

    # 获取A股股票列表
    try:
        stock_info = get_a_share_list()
        # stock_info = get_a_excel_list()
        # 限制数量以进行快速测试
        stock_list = stock_info.head(stock_limit)  # 分析前50只股票
        print(f"获取到 {len(stock_list)} 只股票信息，开始分析...")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"获取股票列表失败: {e}")
        return pd.DataFrame(), pd.DataFrame()

    results = []
    # 准备参数列表
    stock_args = [(row['code'], row['name'], start_date, end_date)
                  for index, row in stock_list.iterrows()]

    # 使用进程池处理股票数据
    max_workers = min(15, len(stock_args))  # 控制进程数量，避免资源占用过高
    print(f"启动 {max_workers} 个进程进行分析...")

    # 使用spawn上下文创建进程池，避免macOS上fork导致的死锁
    mp_context = multiprocessing.get_context('spawn')
    with ProcessPoolExecutor(max_workers=max_workers, mp_context=mp_context) as executor:
        # 提交任务
        future_to_stock = {
            executor.submit(get_single_stock_performance_process, args): args[0:2]
            for args in stock_args
        }

        # 收集结果，设置超时避免永久阻塞
        completed = 0
        successful = 0
        for future in as_completed(future_to_stock):
            try:
                result = future.result()
                if result:
                    results.append(result)
                    successful += 1
            except BaseException as e:
                import traceback
                traceback.print_exc()
                print(f"[ERROR] 处理股票任务时出错: {e}")

            completed += 1
            if completed % 2 == 0 or completed == len(stock_list):
                print(f"进度: 已完成 {completed}/{len(stock_list)} 只股票的处理，成功 {successful} 只")
    # 创建结果DataFrame
    result_df = pd.DataFrame(results)

    # 筛选年化收益率大于等于15%的股票
    high_performers = result_df[result_df['annualized_return_pct'] >= 15].sort_values(
        'annualized_return_pct', ascending=False
    ).reset_index(drop=True)

    print(f"\n总共找到 {len(high_performers)} 只年化收益率≥15%的股票")

    return high_performers, result_df


def main():
    """
    主函数
    """
    print("=" * 60)
    print("使用baostock分析A股市场年化收益率超过15%的股票（多进程版本）")
    print("分析指标包括：年化收益率、总收益率、波动率、夏普比率、最大回撤、胜率等")
    print("=" * 60)

    try:
        # 执行分析
        print("\n开始分析...")
        results, all_results_df = advanced_analysis_with_multiprocessing(stock_limit=10000)  # 减少分析股票数量以加快速度

        if results.empty:
            print("\n未找到年化收益率≥15%的股票")
        else:
            print(f"\n找到 {len(results)} 只年化收益率≥15%的股票")

        # 生成输出文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f"A_15_percent_baostock_mp_{timestamp}.xlsx"

        # 导出结果
        export_results_to_excel(all_results_df, output_filename)

        # 显示统计信息
        high_results_df = all_results_df[all_results_df['annualized_return_pct'] >= 15].sort_values(
            'annualized_return_pct', ascending=False
        ).reset_index(drop=True)

        print(f"\n分析完成！共找到 {len(high_results_df)} 只年化收益率≥15%的股票")

        if len(high_results_df) > 0:
            print("\n前10名高收益股票详情:")
            display_cols = [
                'ts_code', 'name', 'annualized_return_pct',
                'total_return_pct', 'years', 'volatility_pct',
                'sharpe_ratio', 'max_drawdown_pct', 'win_rate_pct'
            ]
            print(high_results_df[display_cols].head(10).to_string(index=False))

            print(f"\n年化收益率分布情况:")
            print(f"最高年化收益率: {high_results_df['annualized_return_pct'].max():.2f}%")
            print(f"最低年化收益率: {high_results_df['annualized_return_pct'].min():.2f}%")
            print(f"平均年化收益率: {high_results_df['annualized_return_pct'].mean():.2f}%")
            print(f"收益率中位数: {high_results_df['annualized_return_pct'].median():.2f}%")


        else:
            print("\n在当前分析的股票中未找到年化收益率≥15%的股票")
            if len(all_results_df) > 0:
                print(f"全部分析股票中的最高年化收益率: {all_results_df['annualized_return_pct'].max():.2f}%")
                print(f"全部分析股票中的平均年化收益率: {all_results_df['annualized_return_pct'].mean():.2f}%")

    except Exception as e:
        print(f"执行过程中出现错误: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
