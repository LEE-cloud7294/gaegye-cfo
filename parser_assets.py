"""
잔고 파서
  파서 α: 국내 / ISA / 연금저축  (pandas 2-row per stock)
  파서 α: 해외                   (openpyxl 2-row per stock)
  파서 β: IRP                   (pandas 2-row per stock, 3-row header)
"""
import pandas as pd
import openpyxl


def parse_assets_domestic(file, account_name: str, market: str = '국내') -> list[dict]:
    """국내 / ISA / 연금저축 잔고 파서"""
    df = pd.read_excel(file, header=None)

    # 데이터 시작행: '보유잔고' 헤더가 있는 행 + 2
    data_start = None
    for idx in range(len(df)):
        row = df.iloc[idx]
        for cell in row:
            if str(cell).strip() == '보유잔고':
                data_start = idx + 2
                break
        if data_start:
            break

    if data_start is None:
        return []

    records = []
    for i in range(data_start, len(df) - 1, 2):
        r1 = df.iloc[i]

        stock_name = str(r1[0]).strip() if pd.notna(r1[0]) else None
        if not stock_name or stock_name == 'nan':
            break

        quantity = r1[8]
        avg_price = r1[12]

        if pd.isna(quantity) or pd.isna(avg_price):
            continue

        records.append({
            'account_name': account_name,
            'market':       market,
            'stock_name':   stock_name,
            'ticker':       None,
            'quantity':     float(quantity),
            'avg_price':    float(avg_price),
            'currency':     'KRW',
        })

    return records


def parse_assets_overseas(file, account_name: str = '일반주식_해외') -> list[dict]:
    """해외 잔고 파서"""
    wb = openpyxl.load_workbook(file, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    records = []
    # 첫 2행 헤더
    for i in range(2, len(rows) - 1, 2):
        r1 = rows[i]
        r2 = rows[i + 1]

        ticker = str(r1[1]).strip() if r1[1] else None
        if not ticker or ticker == 'None':
            break

        stock_name = str(r2[1]).strip() if r2[1] else ticker
        currency = str(r2[0]).strip() if r2[0] else 'USD'
        if currency in ('None', ''):
            currency = 'USD'

        quantity = r1[4]    # 잔고수량
        avg_price_krw = r2[6]  # 매입평균가 (KRW)
        exchange_rate = r1[11]  # 환율

        if not quantity or not avg_price_krw:
            continue

        # USD로 환산하여 저장
        if exchange_rate and float(exchange_rate) > 0:
            avg_price = round(float(avg_price_krw) / float(exchange_rate), 4)
        else:
            avg_price = float(avg_price_krw)

        records.append({
            'account_name': account_name,
            'market':       '해외',
            'stock_name':   stock_name,
            'ticker':       ticker,
            'quantity':     float(quantity),
            'avg_price':    avg_price,
            'currency':     currency,
        })

    return records


def parse_assets_irp(file, account_name: str = 'IRP') -> list[dict]:
    """IRP 자산현황 파서 (3행 헤더, 2행 per 종목)"""
    df = pd.read_excel(file, header=None)

    records = []
    # 데이터 시작: 행 3 (0-indexed)
    for i in range(3, len(df) - 1, 2):
        r1 = df.iloc[i]
        r2 = df.iloc[i + 1]

        stock_name = str(r1[2]).strip() if pd.notna(r1[2]) else None
        if not stock_name or stock_name == 'nan':
            break

        ticker = str(r2[2]).strip() if pd.notna(r2[2]) else None
        if ticker == 'nan':
            ticker = None
        # 숫자로만 된 ticker는 종목코드 (KR... 등 문자 있으면 유효)
        if ticker and ticker.isdigit():
            ticker = None

        quantity = r1[4]        # 보유잔고
        purchase_amt = r1[3]    # 매입원금

        if pd.isna(quantity) or float(quantity) == 0:
            continue
        if pd.isna(purchase_amt):
            continue

        avg_price = round(float(purchase_amt) / float(quantity), 2)

        records.append({
            'account_name': account_name,
            'market':       '국내',
            'stock_name':   stock_name,
            'ticker':       ticker,
            'quantity':     float(quantity),
            'avg_price':    avg_price,
            'currency':     'KRW',
        })

    return records
