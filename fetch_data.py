# fetch_data.py  —  100% Yahoo Finance, no Finviz scraping
import time
import json
from datetime import datetime

import numpy as np
import yfinance as yf

TICKERS = [
    "MU", "NVDA", "GOOGL", "FIX", "MP", "PLTR", "ADBE", "AMD", "AMZN",
    "AAPL", "APLD", "AMAT", "APP", "ARGX", "ANET", "ASML", "ALAB", "AXTI",
    "BDC", "BE", "AVGO", "BWXT", "CDNS", "CALX", "CCJ", "CARR", "LEU",
    "CIEN", "NET", "CEG", "CRWV", "GLW", "CRWD", "DNN", "ETN", "LLY",
    "EME", "EFX", "FCX", "GEV", "IBM", "IESC", "INOD", "INTC",
    "IONQ", "MRVL", "META", "MELI", "MSFT", "MOD", "MLI", "MYRG",
    "NBIS", "NFLX", "ORCL", "PANW", "POWL", "PLD", "PWR", "CRM",
    "STX", "S", "NOW", "SNOW", "SOFI", "SMCI", "SYM", "SNPS",
    "TSM", "TEM", "TSLA", "TXN", "UBER", "VRT", "V", "VST", "WDC", "ZETA",
    "ZS", "CBRS", "MTSI", "ONTO", "LRCX", "TTMI", "MRCY", "COHR", "RSI",
    "TSEM", "SITM", "TER", "CLS", "TPC", "CRDO", "KLIC",
]

ROW_MAP = {
    "0q":  "Current Qtr.",
    "+1q": "Next Qtr.",
    "0y":  "Current Year",
    "+1y": "Next Year",
}

INDEX_MAP = {
    "current":   "Current Estimate",
    "7daysAgo":  "7 Days Ago",
    "30daysAgo": "30 Days Ago",
    "60daysAgo": "60 Days Ago",
    "90daysAgo": "90 Days Ago",
}


def fmt_pct(v):
    """Float 0.xx → '12.34%' string, or N/A."""
    if v is None:
        return "N/A"
    try:
        return f"{float(v) * 100:.2f}%"
    except Exception:
        return "N/A"


def fmt_num(v, decimals=2):
    if v is None:
        return "N/A"
    try:
        return str(round(float(v), decimals))
    except Exception:
        return "N/A"


def fmt_cap(v):
    """Market cap as e.g. '1.23T', '456.78B', '12.34M'."""
    if v is None:
        return "N/A"
    try:
        v = float(v)
        if v >= 1e12:
            return f"{v/1e12:.2f}T"
        if v >= 1e9:
            return f"{v/1e9:.2f}B"
        if v >= 1e6:
            return f"{v/1e6:.2f}M"
        return str(v)
    except Exception:
        return "N/A"


def safe(v):
    """NaN/None → None for JSON."""
    if v is None:
        return None
    try:
        if np.isnan(v):
            return None
    except Exception:
        pass
    return v


def fetch_fundamentals(ticker: str, stock: yf.Ticker, hist_1y, hist_1m) -> dict:
    """
    Build the fundamentals dict that the dashboard expects,
    using only yfinance data + derived calculations.
    """
    info = {}
    try:
        info = stock.info or {}
    except Exception:
        pass

    # ── Helpers ──────────────────────────────────────────────────────────────
    def g(key, default=None):
        v = info.get(key, default)
        return None if v in (None, "N/A", "", "nan") else v

    # ── Market Cap ───────────────────────────────────────────────────────────
    market_cap = fmt_cap(g("marketCap"))

    # ── Valuation ratios ─────────────────────────────────────────────────────
    pe            = fmt_num(g("trailingPE"))
    forward_pe    = fmt_num(g("forwardPE"))
    peg           = fmt_num(g("pegRatio"))
    ps            = fmt_num(g("priceToSalesTrailing12Months"))
    pb            = fmt_num(g("priceToBook"))
    # P/FCF: marketCap / freeCashflow
    pfcf = "N/A"
    try:
        mc  = float(g("marketCap"))
        fcf = float(g("freeCashflow"))
        if fcf and fcf != 0:
            pfcf = fmt_num(mc / fcf)
    except Exception:
        pass

    # ── Financial health ─────────────────────────────────────────────────────
    current_ratio = fmt_num(g("currentRatio"))
    debt_eq       = fmt_num(g("debtToEquity"))

    # ── Growth (yfinance gives these as floats, e.g. 0.80 = 80%) ────────────
    eps_this_y  = fmt_pct(g("earningsGrowth"))        # TTM YoY
    eps_next_y  = fmt_pct(g("earningsQuarterlyGrowth"))
    eps_yoy_ttm = fmt_pct(g("earningsGrowth"))
    sales_yoy   = fmt_pct(g("revenueGrowth"))

    # EPS next 5Y: from growth_estimates DataFrame, row "+5y", column ticker
    eps_next_5y = "N/A"
    try:
        ge = stock.growth_estimates
        if ge is not None and not ge.empty:
            # Row index is period: "+5y"; column is ticker symbol
            if "+5y" in ge.index:
                row = ge.loc["+5y"]
                # column might be ticker or first column
                val = None
                if ticker in row.index:
                    val = row[ticker]
                else:
                    val = row.iloc[0]
                if val is not None and not (isinstance(val, float) and np.isnan(val)):
                    eps_next_5y = f"{float(val) * 100:.2f}%"
    except Exception:
        pass

    # ── Insider ownership ─────────────────────────────────────────────────────
    insider_own = fmt_pct(g("heldPercentInsiders"))

    # ── Returns & Margins ─────────────────────────────────────────────────────
    roe           = fmt_pct(g("returnOnEquity"))
    roa           = fmt_pct(g("returnOnAssets"))
    gross_margin  = fmt_pct(g("grossMargins"))

    # ROIC = NOPAT / Invested Capital
    # NOPAT  = Operating Income × (1 − effective tax rate)
    # InvCap = Total Equity + Total Debt − Cash & Equivalents
    roic = "N/A"
    try:
        inc = stock.income_stmt       # columns = quarters/years, rows = line items
        bal = stock.balance_sheet

        if inc is not None and not inc.empty and bal is not None and not bal.empty:
            # Use most recent annual column (first column)
            inc_col = inc.iloc[:, 0]
            bal_col = bal.iloc[:, 0]

            def get_row(df_col, *candidates):
                for c in candidates:
                    if c in df_col.index:
                        v = df_col[c]
                        if v is not None and not (isinstance(v, float) and np.isnan(v)):
                            return float(v)
                return None

            ebit      = get_row(inc_col, "Operating Income", "EBIT")
            tax_exp   = get_row(inc_col, "Tax Provision", "Income Tax Expense")
            pretax    = get_row(inc_col, "Pretax Income", "Income Before Tax")
            equity    = get_row(bal_col, "Stockholders Equity", "Total Equity Gross Minority Interest", "Common Stock Equity")
            total_debt = get_row(bal_col, "Total Debt", "Long Term Debt And Capital Lease Obligation")
            cash      = get_row(bal_col, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments")

            if all(v is not None for v in [ebit, tax_exp, pretax, equity]) and pretax != 0:
                tax_rate = tax_exp / pretax
                tax_rate = max(0, min(tax_rate, 0.5))   # clamp 0–50%
                nopat    = ebit * (1 - tax_rate)
                inv_cap  = (equity or 0) + (total_debt or 0) - (cash or 0)
                if inv_cap and inv_cap > 0:
                    roic = f"{(nopat / inv_cap) * 100:.2f}%"
    except Exception:
        pass
    oper_margin   = fmt_pct(g("operatingMargins"))
    profit_margin = fmt_pct(g("profitMargins"))

    # ── Technical / derived ──────────────────────────────────────────────────
    beta = fmt_num(g("beta"))

    # SMA200 %: (current price / SMA200 - 1) × 100
    sma200_pct = "N/A"
    try:
        if not hist_1y.empty and len(hist_1y) >= 200:
            sma200 = hist_1y["Close"].iloc[-200:].mean()
            price  = hist_1y["Close"].iloc[-1]
            sma200_pct = f"{(price / sma200 - 1) * 100:.2f}%"
        elif not hist_1y.empty:
            sma200 = hist_1y["Close"].mean()
            price  = hist_1y["Close"].iloc[-1]
            sma200_pct = f"{(price / sma200 - 1) * 100:.2f}%"
    except Exception:
        pass

    # Short Ratio
    short_ratio = fmt_num(g("shortRatio"))

    # RSI (14) from 1-year daily history
    rsi_val = "N/A"
    try:
        closes = hist_1y["Close"].dropna()
        if len(closes) >= 15:
            delta = closes.diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rs    = gain / loss
            rsi_series = 100 - 100 / (1 + rs)
            rsi_val = fmt_num(rsi_series.iloc[-1])
    except Exception:
        pass

    # Performance
    perf_ytd   = "N/A"
    perf_month = "N/A"
    perf_year  = "N/A"
    try:
        if not hist_1y.empty:
            last_close = hist_1y["Close"].iloc[-1]

            # YTD: first trading day of current year
            year_start = hist_1y[hist_1y.index.year == datetime.now().year]["Close"]
            if not year_start.empty:
                perf_ytd = f"{(last_close / year_start.iloc[0] - 1) * 100:.2f}%"

            # 1 Month
            if not hist_1m.empty:
                first_1m = hist_1m["Close"].iloc[0]
                perf_month = f"{(last_close / first_1m - 1) * 100:.2f}%"

            # 1 Year
            first_1y = hist_1y["Close"].iloc[0]
            perf_year = f"{(last_close / first_1y - 1) * 100:.2f}%"
    except Exception:
        pass

    # Target Price
    target_price = fmt_num(g("targetMeanPrice"))

    return {
        "Market Cap":      market_cap,
        "P/E":             pe,
        "Forward P/E":     forward_pe,
        "PEG":             peg,
        "P/S":             ps,
        "P/B":             pb,
        "P/FCF":           pfcf,
        "Current Ratio":   current_ratio,
        "Debt/Eq":         debt_eq,
        "EPS this Y %":    eps_this_y,
        "EPS next Y %":    eps_next_y,
        "EPS next 5Y %":   eps_next_5y,
        "EPS Y/Y TTM %":   eps_yoy_ttm,
        "Sales Y/Y TTM %": sales_yoy,
        "Insider Own %":   insider_own,
        "ROA":             roa,
        "ROE":             roe,
        "ROIC":            roic,
        "Gross Margin":    gross_margin,
        "Oper. Margin":    oper_margin,
        "Profit Margin":   profit_margin,
        "SMA 200 %":       sma200_pct,
        "Short Ratio":     short_ratio,
        "RSI":             rsi_val,
        "Beta":            beta,
        "Perf YTD":        perf_ytd,
        "Perf Month":      perf_month,
        "Perf Year":       perf_year,
        "Target Price":    target_price,
    }


def fetch_eps_trend(stock: yf.Ticker) -> dict | None:
    try:
        trend = stock.get_eps_trend()
        if trend is None or trend.empty:
            return None

        cols_available = [c for c in INDEX_MAP.keys() if c in trend.columns]
        rows_available = [r for r in ROW_MAP.keys() if r in trend.index]
        if not cols_available or not rows_available:
            return None

        sub = trend.loc[rows_available, cols_available].T
        sub.rename(index=INDEX_MAP, columns=ROW_MAP, inplace=True)

        return {
            "rows": list(sub.index),
            "cols": list(sub.columns),
            "data": [[safe(v) for v in row] for row in sub.values.tolist()],
        }
    except Exception as e:
        print(f"  [eps_trend] {e}")
        return None


def fetch_price_and_earnings(stock: yf.Ticker, hist_1y) -> dict | None:
    try:
        price = {
            "dates": [d.strftime("%Y-%m-%d") for d in hist_1y.index],
            "close": hist_1y["Close"].round(2).tolist(),
        }

        earnings = None
        try:
            cal = stock.get_earnings_dates(limit=8)
            if cal is not None and not cal.empty:
                def clean(series):
                    return [safe(v) for v in series.round(2).tolist()]

                earnings = {
                    "dates":            [d.strftime("%Y-%m-%d") for d in cal.index],
                    "eps_estimate":     clean(cal["epsestimate"]),
                    "eps_actual":       clean(cal["epsactual"]),
                    "revenue_estimate": [safe(v) for v in cal["revenueestimate"].tolist()],
                    "revenue_actual":   [safe(v) for v in cal["revenueactual"].tolist()],
                }
        except Exception:
            earnings = None

        return {"price": price, "earnings": earnings}
    except Exception as e:
        print(f"  [price/earnings] {e}")
        return None


def main():
    all_data = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tickers": [],
        "stocks": {},
    }

    total = len(TICKERS)
    print(f"Fetching data for {total} tickers (Yahoo Finance only) …\n")

    for i, ticker in enumerate(TICKERS, 1):
        print(f"[{i:>3}/{total}] {ticker} …", end=" ", flush=True)
        stock_entry = {}

        try:
            stock  = yf.Ticker(ticker)
            hist_1y = stock.history(period="1y")
            hist_1m = stock.history(period="1mo")

            stock_entry["fundamentals"]   = fetch_fundamentals(ticker, stock, hist_1y, hist_1m)
            stock_entry["eps_trend"]      = fetch_eps_trend(stock)
            stock_entry["price_earnings"] = fetch_price_and_earnings(stock, hist_1y)

        except Exception as e:
            print(f"ERROR: {e}")
            stock_entry = {"fundamentals": {}, "eps_trend": None, "price_earnings": None}

        all_data["stocks"][ticker] = stock_entry
        all_data["tickers"].append(ticker)

        print("OK")
        time.sleep(0.5)   # polite rate limiting

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    print("\n✅ Saved → data.json")


if __name__ == "__main__":
    main()
