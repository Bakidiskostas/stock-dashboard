"""
fetch_dashboard_data.py  —  100% Yahoo Finance, no Finviz scraping
Produces the same dashboard_data.json structure as the original.
"""

import time, json, math, warnings
from datetime import datetime

import numpy as np
import yfinance as yf
import pandas as pd

warnings.filterwarnings("ignore")

# ─── TICKERS ────────────────────────────────────────────────────────────────
TICKERS = [
    "AAPL", "ALAB", "AMAT", "AMD", "AMZN", "ANET", "APP", "ARGX", "ASML", "AVGO", "BE", "CALX",
    "CCJ", "CEG", "CLS", "COHR", "CRDO", "CSCO", "ETN",
    "FIX", "GEV", "GOOGL", "KLIC", "LLY", "LRCX", "IBM", "IESC", "INOD", "INTC", "IONQ", "MRVL", "META", "MP",
    "MSFT", "MU", "MTSI", "NBIS", "NET", "NFLX", "NOW", "NVDA", "ONTO", "PLTR", "ROKU",
    "RSI", "S", "SITM", "SNOW", "SPCX", "SYM", "TER", "TSM", "TSEM",
    "TTMI", "V", "VRT", "VST", "WDC", "ZETA"
]

# ─── SCORE LOGIC (unchanged from original) ───────────────────────────────────
SCORE_COLUMNS = {
    "Valuation": ["P/E", "Forward P/E", "PEG", "P/S", "P/B"],
    "Financial":  ["Current Ratio", "Debt/Eq"],
    "Growth":    ["EPS this Y %", "EPS next Y %", "EPS Y/Y TTM %", "Sales Y/Y TTM %"],
    "Return":    ["ROE", "ROA", "ROIC"],
    "Margin":    ["Gross Margin", "Oper. Margin", "Profit Margin"],
    "Trend":     ["SMA 200 %", "Short Ratio"],
}

ROW_MAP   = {"0q": "Current Qtr.", "+1q": "Next Qtr.", "0y": "Current Year", "+1y": "Next Year"}
INDEX_MAP = {"current": "Current Estimate", "7daysAgo": "7 Days Ago",
             "30daysAgo": "30 Days Ago", "60daysAgo": "60 Days Ago", "90daysAgo": "90 Days Ago"}

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def json_safe(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)): return None
    raise TypeError(f"Not serializable: {type(obj)}")

def fmt(val):
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 2)
    except: return None

def fmt_pct(v):
    """Float 0.xx → '12.34%' string, or N/A."""
    if v is None: return "N/A"
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f): return "N/A"
        return f"{f * 100:.2f}%"
    except: return "N/A"

def fmt_num(v, decimals=2):
    if v is None: return "N/A"
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f): return "N/A"
        return str(round(f, decimals))
    except: return "N/A"

def fmt_cap(v):
    if v is None: return "N/A"
    try:
        v = float(v)
        if v >= 1e12: return f"{v/1e12:.2f}T"
        if v >= 1e9:  return f"{v/1e9:.2f}B"
        if v >= 1e6:  return f"{v/1e6:.2f}M"
        return str(v)
    except: return "N/A"

def g(info, key):
    v = info.get(key)
    return None if v in (None, "N/A", "", "nan") else v

# ─── SCORE LOGIC (identical to original) ─────────────────────────────────────
def parse_value(raw):
    if raw in ("N/A", "", "-", None): return None
    s = str(raw).strip().replace("%", "").replace(",", "")
    mult = 1.0
    if s.endswith("B"): mult = 1000; s = s[:-1]
    elif s.endswith("M"): mult = 1.0; s = s[:-1]
    elif s.endswith("K"): mult = 0.001; s = s[:-1]
    try: return float(s) * mult
    except: return None

def get_score(col, raw):
    v = parse_value(raw)
    if v is None: return None
    if col == "P/E":           return 1 if v < 25 else (0 if v <= 80 else -1)
    if col == "Forward P/E":   return 1 if v < 20 else (0 if v <= 60 else -1)
    if col == "PEG":           return 1 if v < 1.5 else (0 if v <= 2 else -1)
    if col == "P/S":           return 1 if v < 6 else (0 if v <= 15 else -1)
    if col == "P/B":           return 1 if v < 4 else (0 if v <= 10 else -1)
    if col == "Current Ratio": return -1 if v < 1 else (0 if v <= 1.1 else 1)
    if col == "Debt/Eq":       return 1 if v < 0.5 else (0 if v <= 0.8 else -1)
    if col in ("EPS this Y %","EPS next Y %","EPS Y/Y TTM %"):
        return 1 if v > 40 else (0 if v >= 20 else -1)
    if col == "Sales Y/Y TTM %": return 1 if v > 20 else (0 if v >= 10 else -1)
    if col in ("ROA","ROE","ROIC"): return 1 if v > 20 else (0 if v >= 10 else -1)
    if col == "Gross Margin":   return 1 if v > 60 else (0 if v >= 50 else -1)
    if col in ("Oper. Margin","Profit Margin"): return 1 if v > 30 else (0 if v >= 15 else -1)
    if col == "SMA 200 %":     return 1 if v >= 0 else -1
    if col == "Short Ratio":   return 1 if v < 2 else (0 if v <= 3 else -1)
    return None

def compute_scores(stock):
    scores = {}
    for sc, srcs in SCORE_COLUMNS.items():
        total, has = 0, False
        for col in srcs:
            s = get_score(col, stock.get(col, "N/A"))
            if s is not None: total += s; has = True
        scores[sc] = total if has else None
    valid = [v for v in scores.values() if v is not None]
    scores["Total Score"] = sum(valid) if valid else None
    return scores

# ─── FUNDAMENTALS FROM YFINANCE ──────────────────────────────────────────────
def get_fundamentals(ticker, t, hist_1y, hist_1m):
    info = {}
    try: info = t.info or {}
    except: pass

    # ── Market Cap ──
    market_cap = fmt_cap(g(info, "marketCap"))

    # ── Valuation ──
    pe         = fmt_num(g(info, "trailingPE"))
    forward_pe = fmt_num(g(info, "forwardPE"))
    peg        = fmt_num(g(info, "pegRatio"))  # may be N/A; fallback computed below after growth
    ps         = fmt_num(g(info, "priceToSalesTrailing12Months"))
    pb         = fmt_num(g(info, "priceToBook"))
    pfcf = "N/A"
    try:
        mc  = float(g(info, "marketCap"))
        fcf = float(g(info, "freeCashflow"))
        if fcf and fcf != 0: pfcf = fmt_num(mc / fcf)
    except: pass

    # ── Financial health ──
    current_ratio = fmt_num(g(info, "currentRatio"))
    # yfinance normally reports debtToEquity as a percentage (80 => 0.80 ratio),
    # but some tickers come back already as a ratio. Values above 5 are treated
    # as percentages; anything smaller is assumed to already be a ratio.
    _de = g(info, "debtToEquity")
    debt_eq = "N/A"
    if _de is not None:
        try:
            _de = float(_de)
            debt_eq = fmt_num(_de / 100 if abs(_de) > 5 else _de)
        except Exception:
            debt_eq = "N/A"

    # ── Growth ──
    # yfinance is inconsistent: growth figures come back either as decimal
    # fractions (0.18) or as already-multiplied percentages (18.0), depending on
    # the field and the library version. Normalise by magnitude.
    def _as_pct(v):
        if v is None:
            return "N/A"
        try:
            f = float(v)
            if math.isnan(f) or math.isinf(f):
                return "N/A"
            # |value| <= 3 is almost certainly a decimal fraction (<=300% growth);
            # anything larger is already expressed in percent.
            if abs(f) <= 3:
                f *= 100
            return f"{f:.2f}%"
        except Exception:
            return "N/A"

    # EPS Y/Y TTM & Sales come from actual trailing info fields
    eps_yoy_ttm = _as_pct(g(info, "earningsGrowth"))
    sales_yoy   = _as_pct(g(info, "revenueGrowth"))

    # EPS this Y (0y) & next Y (+1y) come from analyst growth_estimates
    eps_this_y = "N/A"
    eps_next_y = "N/A"
    try:
        ge = t.growth_estimates
        if ge is not None and not ge.empty:
            # First column holds the estimate (name varies: 'stockTrend'/ticker)
            col0 = ge.columns[0]
            if "0y" in ge.index:
                eps_this_y = _as_pct(ge.loc["0y", col0])
            if "+1y" in ge.index:
                eps_next_y = _as_pct(ge.loc["+1y", col0])
    except Exception:
        pass

    # ── PEG fallback: if yfinance didn't provide it, compute PE / (EPS next-year growth %) ──
    if peg == "N/A":
        try:
            pe_val = float(pe) if pe != "N/A" else float(forward_pe)
            growth_val = float(eps_next_y.replace("%", "")) if eps_next_y != "N/A" else None
            if pe_val and growth_val and growth_val > 0:
                peg = fmt_num(pe_val / growth_val)
        except Exception:
            pass

    # ── Insider ownership ──
    insider_own = fmt_pct(g(info, "heldPercentInsiders"))

    # ── Returns ──
    roe = fmt_pct(g(info, "returnOnEquity"))
    roa = fmt_pct(g(info, "returnOnAssets"))

    # ROIC = NOPAT / Invested Capital
    roic = "N/A"
    try:
        inc = t.income_stmt
        bal = t.balance_sheet
        if inc is not None and not inc.empty and bal is not None and not bal.empty:
            ic = inc.iloc[:, 0]
            bc = bal.iloc[:, 0]
            def get_row(col, *candidates):
                for c in candidates:
                    if c in col.index:
                        v = col[c]
                        if v is not None and not (isinstance(v, float) and math.isnan(v)):
                            return float(v)
                return None
            ebit     = get_row(ic, "Operating Income", "EBIT")
            tax_exp  = get_row(ic, "Tax Provision", "Income Tax Expense")
            pretax   = get_row(ic, "Pretax Income", "Income Before Tax")
            equity   = get_row(bc, "Stockholders Equity", "Total Equity Gross Minority Interest", "Common Stock Equity")
            tot_debt = get_row(bc, "Total Debt", "Long Term Debt And Capital Lease Obligation")
            cash     = get_row(bc, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments")
            if all(v is not None for v in [ebit, tax_exp, pretax, equity]) and pretax != 0:
                tax_rate = max(0, min(tax_exp / pretax, 0.5))
                nopat    = ebit * (1 - tax_rate)
                inv_cap  = (equity or 0) + (tot_debt or 0) - (cash or 0)
                if inv_cap and inv_cap > 0:
                    roic = f"{(nopat / inv_cap) * 100:.2f}%"
    except: pass

    # ── Margins ──
    gross_margin  = fmt_pct(g(info, "grossMargins"))
    oper_margin   = fmt_pct(g(info, "operatingMargins"))
    profit_margin = fmt_pct(g(info, "profitMargins"))

    # ── Technical / derived ──
    beta = fmt_num(g(info, "beta"))

    # SMA 200 %
    sma200_pct = "N/A"
    try:
        if not hist_1y.empty:
            closes = hist_1y["Close"].dropna()
            n = min(200, len(closes))
            sma200 = closes.iloc[-n:].mean()
            price  = closes.iloc[-1]
            sma200_pct = f"{(price / sma200 - 1) * 100:.2f}%"
    except: pass

    short_ratio = fmt_num(g(info, "shortRatio"))

    # RSI (14)
    rsi_val = "N/A"
    try:
        closes = hist_1y["Close"].dropna()
        if len(closes) >= 15:
            delta = closes.diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rs    = gain / loss
            rsi_val = fmt_num((100 - 100 / (1 + rs)).iloc[-1])
    except: pass

    # Performance
    perf_ytd = perf_month = perf_year = "N/A"
    try:
        if not hist_1y.empty:
            last = hist_1y["Close"].iloc[-1]
            yr_data = hist_1y[hist_1y.index.year == datetime.now().year]["Close"]
            if not yr_data.empty:
                perf_ytd = f"{(last / yr_data.iloc[0] - 1) * 100:.2f}%"
            if not hist_1m.empty:
                perf_month = f"{(last / hist_1m['Close'].iloc[0] - 1) * 100:.2f}%"
            perf_year = f"{(last / hist_1y['Close'].iloc[0] - 1) * 100:.2f}%"
    except: pass

    target_price = fmt_num(g(info, "targetMeanPrice"))

    return {
        "Ticker":          ticker,
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

# ─── YFINANCE DATA FUNCTIONS (unchanged from original) ───────────────────────
def get_eps_trend(t):
    try:
        trend = t.get_eps_trend()
        if trend is None or trend.empty: return None
        cols = [c for c in INDEX_MAP if c in trend.columns]
        rows = [r for r in ROW_MAP if r in trend.index]
        if not cols or not rows: return None
        sub = trend.loc[rows, cols].T
        sub.rename(index=INDEX_MAP, columns=ROW_MAP, inplace=True)
        result = {}
        for period in sub.columns:
            result[period] = {est: fmt(sub.loc[est, period]) for est in sub.index}
        return result
    except: return None

def get_earnings_history(t):
    try:
        hist = t.earnings_history
        if hist is None or hist.empty: return []
        records = [{"date": str(idx)[:10], "epsEstimate": fmt(row.get("epsEstimate")),
                    "epsActual": fmt(row.get("epsActual")), "epsDiff": fmt(row.get("epsDifference")),
                    "surprisePct": fmt(row.get("surprisePercent"))} for idx, row in hist.iterrows()]
        return records[-8:] if len(records) > 8 else records
    except: return []

def get_price_history(t):
    result = {}
    for key, (period, interval) in {"1y":("1y","1d"),"6m":("6mo","1d"),"1m":("1mo","1d"),"1w":("5d","1h")}.items():
        try:
            hist = t.history(period=period, interval=interval)
            if hist.empty: result[key] = []; continue
            records = []
            for ts, row in hist.iterrows():
                o,h,l,c = float(row["Open"]),float(row["High"]),float(row["Low"]),float(row["Close"])
                if any(math.isnan(x) for x in [o,h,l,c]): continue
                records.append({"t":str(ts)[:16],"o":round(o,2),"h":round(h,2),"l":round(l,2),"c":round(c,2),"v":int(row["Volume"])})
            result[key] = records
        except: result[key] = []
    return result

def get_forward_pe_history(t, info):
    try:
        stmt = t.income_stmt
        if stmt is None or stmt.empty or "Diluted EPS" not in stmt.index: return []
        eps_row = stmt.loc["Diluted EPS"]
        items = sorted([(col, eps_row[col]) for col in stmt.columns], key=lambda x: x[0])
        dates = [d for d, _ in items]
        eps_vals = [v for _, v in items]
        hist = t.history(period="5y", interval="1d")
        if hist.empty: return []
        def price_near(target_ts):
            try:
                sub = hist[hist.index <= target_ts]
                if sub.empty: sub = hist
                return float(sub["Close"].iloc[-1])
            except: return None
        points = []
        for i in range(len(dates) - 1):
            d, next_eps = dates[i], eps_vals[i + 1]
            if next_eps is None or (isinstance(next_eps, float) and (math.isnan(next_eps) or next_eps == 0)): continue
            px = price_near(d.tz_localize(hist.index.tz) if hist.index.tz is not None and d.tzinfo is None else d)
            if px is None: continue
            pe = px / float(next_eps)
            if math.isnan(pe) or math.isinf(pe): continue
            points.append({"label": str(d)[:7], "pe": round(pe, 2)})
        cur_price = info.get("price")
        fwd_eps   = info.get("epsForward")
        if cur_price and fwd_eps and fwd_eps != 0:
            pe = cur_price / fwd_eps
            if not (math.isnan(pe) or math.isinf(pe)):
                points.append({"label": "Now", "pe": round(pe, 2)})
        return points
    except: return []

def get_next_earnings(t, info):
    try:
        cal = t.calendar
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            if isinstance(ed, list) and ed: return str(ed[0])[:10]
            if ed: return str(ed)[:10]
    except: pass
    try:
        ed = info.get("earningsDate")
        if isinstance(ed, list) and ed: return str(ed[0])[:10]
    except: pass
    try:
        ts = info.get("earningsTimestamp")
        if ts:
            from datetime import datetime as _dt
            return _dt.utcfromtimestamp(ts).strftime("%Y-%m-%d")
    except: pass
    return None

def get_yf_info(t):
    try:
        info = t.info
        return {
            "name": info.get("longName",""), "price": fmt(info.get("currentPrice") or info.get("regularMarketPrice")),
            "prevClose": fmt(info.get("previousClose")), "change": None, "changePct": None,
            "marketCap": info.get("marketCap"), "pe": fmt(info.get("trailingPE")),
            "forwardPE": fmt(info.get("forwardPE")), "eps": fmt(info.get("trailingEps")),
            "epsForward": fmt(info.get("forwardEps")), "revenue": info.get("totalRevenue"),
            "sector": info.get("sector",""), "industry": info.get("industry",""),
            "52wHigh": fmt(info.get("fiftyTwoWeekHigh")), "52wLow": fmt(info.get("fiftyTwoWeekLow")),
            "avgVolume": info.get("averageVolume"), "beta": fmt(info.get("beta")),
            "targetPrice": fmt(info.get("targetMeanPrice")), "recommendation": info.get("recommendationKey",""),
            "nextEarnings": get_next_earnings(t, info),
        }
    except: return {}

# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    json_file = "dashboard_data.json"
    total = len(TICKERS)

    print(f"\n{'='*55}")
    print(f"  Stock Dashboard — Yahoo Finance only ({total} tickers)")
    print(f"{'='*55}\n")

    all_data = {}
    for i, ticker in enumerate(TICKERS, 1):
        print(f"  [{i:>2}/{total}] {ticker}...", end=" ", flush=True)
        try:
            t        = yf.Ticker(ticker)
            info     = get_yf_info(t)
            hist_1y  = t.history(period="1y")
            hist_1m  = t.history(period="1mo")

            fv = get_fundamentals(ticker, t, hist_1y, hist_1m)
            scores   = compute_scores(fv)

            price = info.get("price"); prev = info.get("prevClose")
            if price and prev and prev != 0:
                info["change"]    = round(price - prev, 2)
                info["changePct"] = round((price - prev) / prev * 100, 2)

            all_data[ticker] = {
                "info":         info,
                "finviz":       fv,        # same key name — dashboard reads this
                "scores":       scores,
                "epsTrend":     get_eps_trend(t),
                "earningsHist": get_earnings_history(t),
                "priceHist":    get_price_history(t),
                "fwdPeHist":    get_forward_pe_history(t, info),
            }
            print("OK")
        except Exception as e:
            print(f"FAILED ({e})")
            all_data[ticker] = {"info": {"name": ticker}, "finviz": {}, "scores": {},
                                "epsTrend": None, "earningsHist": [], "priceHist": {}, "fwdPeHist": []}
        time.sleep(0.5)

    payload = {
        "lastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tickers": TICKERS,
        "data": all_data,
    }
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, default=json_safe)

    print(f"\n✅ Done! Saved → {json_file}")
    print("   Run: git add -f dashboard_data.json && git commit -m 'update' && git push")

if __name__ == "__main__":
    main()
