"""Fundamental data fetching via yfinance.

Fallback chain for revenue YoY growth:
  1. quarterly_financials (best — TTM from 8 quarters)
  2. financials / income_stmt (annual — YoY from consecutive years)
  3. ticker.info["revenueGrowth"] (pre-computed TTM, cheapest fallback)

data_quality dict in the return value reports which source was used so
the Claude prompt can note stale or low-confidence fields.
"""
import yfinance as yf


def _revenue_row(fin):
    """Return the revenue Series from a financials DataFrame, or None."""
    if fin is None or fin.empty:
        return None
    for label in ["Total Revenue", "Revenue"]:
        if label in fin.index:
            return fin.loc[label]
    matches = [idx for idx in fin.index if "Revenue" in str(idx)]
    if matches:
        return fin.loc[matches[0]]
    return None


def get_fundamentals(symbol: str) -> dict:
    """Fetch fundamental data for a symbol.

    Returns a dict with keys:
        symbol, revenue_ttm, revenue_yoy_growth, fcf_ttm,
        gross_margin, operating_margin, debt_to_equity,
        data_quality (dict — source used for each derived field)
    All financial fields are float | None.
    """
    dq: dict[str, str] = {
        "revenue_yoy_growth": "missing",
        "fcf_ttm": "missing",
    }
    empty = {
        "symbol": symbol,
        "revenue_ttm": None,
        "revenue_yoy_growth": None,
        "fcf_ttm": None,
        "gross_margin": None,
        "operating_margin": None,
        "debt_to_equity": None,
        "data_quality": dq,
    }

    try:
        ticker = yf.Ticker(symbol)

        # ── Revenue (quarterly first) ────────────────────────────────────────
        revenue_ttm = None
        revenue_prior = None
        gross_profit_q = None
        operating_income_q = None

        try:
            fin = ticker.quarterly_financials
            rev_row = _revenue_row(fin)
            if rev_row is not None:
                rev_vals = rev_row.dropna().values
                if len(rev_vals) >= 4:
                    revenue_ttm = float(sum(rev_vals[:4]))
                elif len(rev_vals) > 0:
                    revenue_ttm = float(sum(rev_vals))
                if len(rev_vals) >= 8:
                    revenue_prior = float(sum(rev_vals[4:8]))
                    dq["revenue_yoy_growth"] = "quarterly"

                if fin is not None and "Gross Profit" in fin.index:
                    gp_vals = fin.loc["Gross Profit"].dropna().values
                    if len(gp_vals) > 0:
                        gross_profit_q = float(gp_vals[0])

                if fin is not None:
                    for oi_label in ["Operating Income", "EBIT"]:
                        if oi_label in fin.index:
                            oi_vals = fin.loc[oi_label].dropna().values
                            if len(oi_vals) > 0:
                                operating_income_q = float(oi_vals[0])
                            break
        except Exception as e:
            print(f"  [warn] {symbol} quarterly_financials: {e}")

        # ── Revenue YoY fallback 1: annual financials ────────────────────────
        if revenue_prior is None:
            for attr in ("financials", "income_stmt"):
                try:
                    annual_fin = getattr(ticker, attr)
                    rev_row = _revenue_row(annual_fin)
                    if rev_row is not None:
                        ann_vals = rev_row.dropna().values
                        if len(ann_vals) >= 2:
                            revenue_prior = float(ann_vals[1])
                            dq["revenue_yoy_growth"] = "annual"
                            if revenue_ttm is None and len(ann_vals) >= 1:
                                revenue_ttm = float(ann_vals[0])
                            break
                        elif len(ann_vals) == 1 and revenue_ttm is None:
                            revenue_ttm = float(ann_vals[0])
                except Exception as e:
                    print(f"  [warn] {symbol} {attr}: {e}")

        # ── Revenue YoY fallback 2: ticker.info["revenueGrowth"] ────────────
        if revenue_prior is None:
            try:
                info = ticker.info or {}
                growth = info.get("revenueGrowth")
                if growth is not None:
                    # revenueGrowth is a fraction (e.g. 0.12 = 12% YoY)
                    if revenue_ttm is None:
                        ttm_from_info = info.get("totalRevenue")
                        if ttm_from_info:
                            revenue_ttm = float(ttm_from_info)
                    if revenue_ttm is not None and growth != -1.0:
                        revenue_prior = revenue_ttm / (1.0 + float(growth))
                        dq["revenue_yoy_growth"] = "info.revenueGrowth"
            except Exception as e:
                print(f"  [warn] {symbol} ticker.info revenueGrowth: {e}")

        revenue_yoy_growth = None
        if revenue_ttm is not None and revenue_prior is not None and revenue_prior != 0:
            revenue_yoy_growth = (revenue_ttm - revenue_prior) / abs(revenue_prior)
        if revenue_yoy_growth is None:
            dq["revenue_yoy_growth"] = "missing"

        # ── FCF (quarterly first) ────────────────────────────────────────────
        fcf_ttm = None
        try:
            cf = ticker.quarterly_cashflow
            if cf is not None and not cf.empty:
                fcf_row = None
                if "Free Cash Flow" in cf.index:
                    fcf_row = cf.loc["Free Cash Flow"]
                else:
                    matches = [idx for idx in cf.index if "Free Cash Flow" in str(idx)]
                    if matches:
                        fcf_row = cf.loc[matches[0]]
                if fcf_row is not None:
                    fcf_vals = fcf_row.dropna().values
                    if len(fcf_vals) >= 4:
                        fcf_ttm = float(sum(fcf_vals[:4]))
                        dq["fcf_ttm"] = "quarterly"
                    elif len(fcf_vals) > 0:
                        fcf_ttm = float(sum(fcf_vals))
                        dq["fcf_ttm"] = "quarterly"
        except Exception as e:
            print(f"  [warn] {symbol} quarterly_cashflow: {e}")

        # ── FCF fallback: annual cashflow ────────────────────────────────────
        if fcf_ttm is None:
            for attr in ("cashflow", "cash_flow"):
                try:
                    annual_cf = getattr(ticker, attr, None)
                    if annual_cf is None or annual_cf.empty:
                        continue
                    fcf_row = None
                    if "Free Cash Flow" in annual_cf.index:
                        fcf_row = annual_cf.loc["Free Cash Flow"]
                    else:
                        matches = [idx for idx in annual_cf.index if "Free Cash Flow" in str(idx)]
                        if matches:
                            fcf_row = annual_cf.loc[matches[0]]
                    if fcf_row is not None:
                        fcf_vals = fcf_row.dropna().values
                        if len(fcf_vals) > 0:
                            fcf_ttm = float(fcf_vals[0])
                            dq["fcf_ttm"] = "annual"
                            break
                except Exception as e:
                    print(f"  [warn] {symbol} {attr}: {e}")

        # ── Margins (from quarterly revenue) ────────────────────────────────
        gross_margin = None
        operating_margin = None
        try:
            fin = ticker.quarterly_financials
            rev_row = _revenue_row(fin)
            if rev_row is not None:
                rev_vals = rev_row.dropna().values
                if len(rev_vals) > 0:
                    rev_q = float(rev_vals[0])
                    if rev_q != 0:
                        if gross_profit_q is not None:
                            gross_margin = gross_profit_q / rev_q
                        if operating_income_q is not None:
                            operating_margin = operating_income_q / rev_q
        except Exception as e:
            print(f"  [warn] {symbol} margins: {e}")

        # ── Debt-to-Equity ────────────────────────────────────────────────────
        debt_to_equity = None
        try:
            bs = ticker.quarterly_balance_sheet
            if bs is not None and not bs.empty:
                debt = None
                for d_label in ["Total Debt", "Long Term Debt", "Short Long Term Debt"]:
                    if d_label in bs.index:
                        d_vals = bs.loc[d_label].dropna().values
                        if len(d_vals) > 0:
                            debt = float(d_vals[0])
                        break

                equity = None
                for e_label in [
                    "Stockholders Equity",
                    "Total Stockholders Equity",
                    "Common Stock Equity",
                ]:
                    if e_label in bs.index:
                        e_vals = bs.loc[e_label].dropna().values
                        if len(e_vals) > 0:
                            equity = float(e_vals[0])
                        break

                if debt is not None and equity is not None and equity != 0:
                    debt_to_equity = debt / equity
        except Exception as e:
            print(f"  [warn] {symbol} balance_sheet: {e}")

        return {
            "symbol": symbol,
            "revenue_ttm": revenue_ttm,
            "revenue_yoy_growth": revenue_yoy_growth,
            "fcf_ttm": fcf_ttm,
            "gross_margin": gross_margin,
            "operating_margin": operating_margin,
            "debt_to_equity": debt_to_equity,
            "data_quality": dq,
        }

    except Exception as exc:
        print(f"  [warn] fundamentals {symbol}: {exc}")
        return empty
