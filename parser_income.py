"""
거래내역 파서
  파서 A: 일반주식(국내+해외) / ISA / 연금저축
  파서 B: IRP

[해외 배당 USD 금액 추출 우선순위]
  ① r2[13] 외화정산금액  — KB증권이 실수령 USD를 여기 기록 (가장 신뢰)
  ② r1[3]  거래금액      — gross USD (일부 구형 데이터)
  ③ 외화예수금 차분      — 최후 수단 (KRW 거래가 외화예수금을 0으로 오염시키므로
                            USD 거래 시에만 prev_usd 갱신)
"""
import pandas as pd

_A_MAP = {
    '예탁금이용료 입금':    '이자_예탁금',
    '해외원천세 환급 입금': '세금환급',
    '전자금융입금':        '신규투자',
    '은행이체 입금':       '신규투자',
    '대체입금':           '계좌이체',
    '대체출금':           '계좌이체',
}

_A_SKIP = {
    '주식장내매수', 'KOSDAQ매수', '매수',
    '주식장내매도', 'KOSDAQ매도', '매도',
    '글로벌원마켓플러스외화매수 출금', '외화매도',
    '전자금융송금 출금',
    '해외원천세 출금', '배당세금추징 출금', '이자소득세추징 출금',
    '액면분할 입고', '액면분할 출고',
}


def _pos(v) -> float | None:
    """NaN/0/음수 → None, 양수 float 반환"""
    if v is None or (isinstance(v, float) and (pd.isna(v) or v <= 0)):
        return None
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def parse_income_a(file, account_name: str) -> list[dict]:
    """
    account_name: '일반주식' | 'ISA' | '연금저축'
    '일반주식' 선택 시 통화구분으로 _국내 / _해외 자동 분리
    """
    df = pd.read_excel(file, header=None)
    records = []
    prev_usd = 0.0

    for i in range(2, len(df) - 1, 2):
        r1 = df.iloc[i]
        r2 = df.iloc[i + 1]

        trade_date = r1[0]
        trade_type = str(r1[1]).strip() if pd.notna(r1[1]) else ''

        # 빈 행 — USD 거래면 prev_usd 갱신
        if not trade_date or not trade_type:
            if pd.notna(r2[11]) and str(r1[11] if pd.notna(r1[11]) else '').strip() == 'USD':
                prev_usd = float(r2[11])
            continue

        if hasattr(trade_date, 'date'):
            trade_date = trade_date.date()

        currency = str(r1[11]).strip() if pd.notna(r1[11]) else ''
        usd_bal  = float(r2[11]) if pd.notna(r2[11]) else prev_usd

        # 건너뛸 거래 — USD 거래만 prev_usd 갱신 (KRW 거래는 갱신 금지)
        if trade_type in _A_SKIP or (trade_type not in _A_MAP and trade_type != '배당금 입금'):
            if currency == 'USD':
                prev_usd = usd_bal
            continue

        acct = ('일반주식_해외' if currency == 'USD' else '일반주식_국내') \
               if account_name == '일반주식' else account_name

        stock_name = str(r2[1]).strip() if pd.notna(r2[1]) else None
        if stock_name == 'nan':
            stock_name = None

        tax = ((_pos(r1[6]) or 0) + (_pos(r2[5]) or 0) + (_pos(r2[6]) or 0))

        amount_krw = amount_usd = exchange_rate = net_krw = None

        if trade_type == '배당금 입금':
            if currency == 'USD':
                income_type  = '배당_해외'
                exchange_rate = _pos(r1[12])

                # ① 외화정산금액 (실수령 USD — 최우선)
                amt = _pos(r2[13]) or _pos(r1[3])
                if amt is None:
                    # ② 외화예수금 차분 (최후)
                    amt = round(usd_bal - prev_usd, 6) if usd_bal > prev_usd else None

                amount_usd = amt
                if exchange_rate and amount_usd:
                    net_krw = round(amount_usd * exchange_rate)
            else:
                income_type = '배당_국내'
                amount_krw  = _pos(r1[3])
                net_krw     = _pos(r1[4]) or amount_krw

        elif trade_type == '대체출금':
            income_type = '계좌이체'
            v = _pos(r1[3])
            amount_krw = -v if v else None
            v2 = _pos(r1[4])
            net_krw    = -v2 if v2 else None

        else:
            income_type = _A_MAP[trade_type]
            if currency == 'USD':
                # 해외계좌 이자_예탁금/세금환급 등 — 외화정산금액(r2[13])·환율(r1[12]) 컬럼 사용
                # (배당_해외와 동일한 컬럼 위치, 금액은 보통 소액(센트 단위))
                exchange_rate = _pos(r1[12])
                amount_usd    = _pos(r2[13])
                if exchange_rate and amount_usd:
                    net_krw = round(amount_usd * exchange_rate)
            else:
                amount_krw  = _pos(r1[3]) or _pos(r1[4])
                net_krw     = _pos(r1[4]) or _pos(r1[3])

        records.append({
            'date':           str(trade_date),
            'account_name':   acct,
            'stock_name':     stock_name,
            'income_type':    income_type,
            'amount_krw':     amount_krw,
            'amount_usd':     amount_usd,
            'exchange_rate':  exchange_rate,
            'tax_krw':        tax or None,
            'net_amount_krw': net_krw,
        })

        if currency == 'USD':
            prev_usd = usd_bal

    return records


_B_MAP = {
    '배당금 입금':              '배당_국내',
    '현금자산이자(퇴직연금) 입금': '이자_현금자산',
    '채권이자(퇴직연금) 입금':    '이자_채권',
    '기본부담금(퇴직연금) 입금':  '신규투자',
}
_B_SKIP = {'운용지시(퇴직연금) 매수'}


def parse_income_b(file, account_name: str = 'IRP') -> list[dict]:
    df = pd.read_excel(file, header=None)
    records = []

    for i in range(2, len(df) - 1, 2):
        r1 = df.iloc[i]
        r2 = df.iloc[i + 1]

        trade_date = r1[0]
        trade_type = str(r1[1]).strip() if pd.notna(r1[1]) else ''

        if not trade_date or not trade_type:
            continue
        if trade_type in _B_SKIP or trade_type not in _B_MAP:
            continue
        if hasattr(trade_date, 'date'):
            trade_date = trade_date.date()

        stock_name = str(r2[1]).strip() if pd.notna(r2[1]) else None
        if stock_name == 'nan':
            stock_name = None

        tax = ((_pos(r1[5]) or 0) + (_pos(r2[4]) or 0) + (_pos(r2[5]) or 0))
        amount_krw = _pos(r1[3])
        net_krw    = _pos(r1[7]) or amount_krw

        records.append({
            'date':           str(trade_date),
            'account_name':   account_name,
            'stock_name':     stock_name,
            'income_type':    _B_MAP[trade_type],
            'amount_krw':     amount_krw,
            'amount_usd':     None,
            'exchange_rate':  None,
            'tax_krw':        tax or None,
            'net_amount_krw': net_krw,
        })

    return records
