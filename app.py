
"""International Cost of Capital — Kellogg International Finance."""

import io
import re
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import streamlit as st
import pycountry
from bs4 import BeautifulSoup

st.set_page_config(
    page_title="International Cost of Capital",
    page_icon="🌍",
    layout="wide",
)

BETA_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls"
SPREAD_URL = "https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ratings.html"
OECD_URL = "https://www.oecd.org/en/publications/corporate-tax-statistics-2024_9c27d6e8-en/full-report/statutory-corporate-income-tax-rates_440f9286.html"
TE_URL = "https://tradingeconomics.com/bonds"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Explicitly dated classroom reference values, not live market data.
CLASS_TAX_2026 = {
    "United States": 25.5, "Canada": 26.0,
    "Mexico": 30.0, "United Kingdom": 25.0,
    "Germany": 30.1, "France": 36.1,
    "Japan": 29.7, "China": 25.0,
    "India": 25.2, "Australia": 30.0,
    "Colombia": 35.0, "Thailand": 20.0,
    "Singapore": 17.0, "Indonesia": 22.0,
    "Vietnam": 20.0, "Malaysia": 24.0,
    "Philippines": 25.0, "South Korea": 27.5,
    "Switzerland": 19.5, "Ireland": 12.5,
    "Italy": 27.8, "Spain": 25.0,
    "Netherlands": 25.8, "Sweden": 20.6,
    "Norway": 22.0, "Denmark": 22.0,
    "Poland": 19.0, "Portugal": 29.5,
    "New Zealand": 28.0, "Chile": 27.0,
    "Peru": 29.5, "South Africa": 27.0,
    "Turkey": 25.0, "Argentina": 35.0,
    "Belgium": 25.0, "Austria": 23.0,
    "Finland": 20.0, "Greece": 22.0,
    "Israel": 23.0, "Czech Republic": 21.0,
    "Hungary": 9.0, "United Arab Emirates": 9.0,
}

CLASS_YIELDS_NOV6 = {
    "United States": 4.9, "Brazil": 15.2,
    "Colombia": 12.8, "Mexico": 9.1,
    "India": 7.2, "Poland": 6.2,
    "United Kingdom": 5.2, "Australia": 5.0,
    "France": 4.8, "Slovakia": 4.2,
    "Portugal": 3.7, "Canada": 3.7,
    "Germany": 3.3, "Japan": 2.6,
    "China": 1.6, "Switzerland": 0.4,
}

ALIASES = {
    "US": "United States",
    "USA": "United States",
    "UK": "United Kingdom",
    "Britain": "United Kingdom",
    "Korea": "South Korea",
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
    "Turkiye": "Turkey",
    "UAE": "United Arab Emirates",
    "Viet Nam": "Vietnam",
    "Korea, Republic of": "South Korea",
}

def normal_country(value):
    name = re.sub(r"\s+", " ", str(value)).strip()
    return ALIASES.get(name, name)


def parse_num(value):
    if pd.isna(value):
        return None
    s = str(value).replace(",", "").replace("%", "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(match.group()) if match else None


def fetch(url, timeout=25):
    response = requests.get(
        url, headers=HEADERS, timeout=timeout
    )
    response.raise_for_status()
    return response


# --------------------------------------------------
# DAMODARAN INDUSTRY BETAS
# --------------------------------------------------

def get_betas():
    content = fetch(BETA_URL).content
    book = pd.ExcelFile(io.BytesIO(content))

    for sheet in book.sheet_names:
        raw = pd.read_excel(
            io.BytesIO(content),
            sheet_name=sheet,
            header=None,
        )

        for i in range(min(20, len(raw))):
            header = [
                str(v).strip().lower()
                for v in raw.iloc[i]
            ]

            ind = next(
                (j for j, v in enumerate(header)
                 if "industry name" in v or v == "industry"),
                None,
            )

            beta = next(
                (j for j, v in enumerate(header)
                 if "unlevered beta" in v
                 and "cash" not in v
                 and "corrected" not in v),
                None,
            )

            if ind is None or beta is None:
                continue

            out = raw.iloc[i + 1:, [ind, beta]].copy()
            out.columns = ["Industry", "Unlevered beta"]

            out["Unlevered beta"] = pd.to_numeric(
                out["Unlevered beta"], errors="coerce"
            )

            out = out.dropna()
            out["Industry"] = out["Industry"].astype(str).str.strip()

            out = out[
                (out["Unlevered beta"] >= 0)
                & (out["Unlevered beta"] < 10)
                & (~out["Industry"].str.contains(
                    "total market", case=False
                ))
            ]

            if len(out) > 10:
                return (
                    out.drop_duplicates("Industry")
                    .sort_values("Industry")
                    .reset_index(drop=True)
                )

    raise ValueError("Damodaran beta columns not found")


# --------------------------------------------------
# DAMODARAN BBB BORROWING SPREAD
# --------------------------------------------------

def get_spread():
    html = fetch(SPREAD_URL).text
    tables = pd.read_html(io.StringIO(html), flavor="lxml")

    for table in tables:
        columns = [str(c).lower() for c in table.columns]

        for _, row in table.iterrows():
            cells = [str(v).strip() for v in row]

            if not any(
                re.search(r"\b(Baa2|BBB)\b", c, re.I)
                for c in cells
            ):
                continue

            candidates = [
                parse_num(c)
                for c in cells
                if "%" in c and parse_num(c) is not None
            ]

            if candidates:
                return candidates[0], (
                    "First percentage spread on Baa2/BBB row; "
                    "verify large non-financial firm column"
                )

            spread_cols = [
                j for j, c in enumerate(columns)
                if "spread" in c
            ]

            if spread_cols:
                value = parse_num(cells[spread_cols[0]])
                if value is not None:
                    return value, "Baa2/BBB spread column"

    raise ValueError(
        "Could not safely identify the BBB spread. "
        "Use manual override."
    )


# --------------------------------------------------
# OECD CORPORATE TAX EXCEL
# --------------------------------------------------

def get_oecd_taxes():
    path = (
        Path(__file__).resolve().parent
        / "oecd_corporate_tax_2024.xlsx"
    )

    if not path.exists():
        raise FileNotFoundError(
            "Upload oecd_corporate_tax_2024.xlsx "
            "to the repository root."
        )

    raw = pd.read_excel(
        path, sheet_name="g2_1", header=None
    )

    result = {}

    for code, value in raw.iloc[:, :2].itertuples(
        index=False, name=None
    ):
        if not isinstance(code, str):
            continue

        if not re.fullmatch(r"[A-Z]{3}", code):
            continue

        if not isinstance(value, (int, float, np.number)):
            continue

        if pd.isna(value):
            continue

        country = pycountry.countries.get(alpha_3=code)

        if country is None:
            continue

        name = normal_country(country.name)
        result[name] = float(value) * 100

    if not result:
        raise ValueError("No OECD tax rates found")

    return result


# --------------------------------------------------
# TRADING ECONOMICS — DIAGNOSTIC AND PARSER
# --------------------------------------------------

def get_te_yields():
    """
    Uses only the professor-assigned Trading Economics
    bonds webpage. Returns yields and diagnostic details.
    """
    diagnostics = {
        "URL": TE_URL,
        "HTTP status": "Not received",
        "Final URL": "",
        "Response length": 0,
        "HTML table count": 0,
        "HTML row count": 0,
        "10-year candidate rows": 0,
        "Response preview": "",
        "Error": "",
    }

    yields = {}

    try:
        response = requests.get(
            TE_URL,
            headers=HEADERS,
            timeout=30,
        )

        diagnostics["HTTP status"] = response.status_code
        diagnostics["Final URL"] = response.url
        diagnostics["Response length"] = len(response.text)
        diagnostics["Response preview"] = response.text[:1500]

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        diagnostics["HTML table count"] = len(
            soup.select("table")
        )

        rows = soup.select("tr")
        diagnostics["HTML row count"] = len(rows)

        for tr in rows:
            cells = [
                c.get_text(" ", strip=True)
                for c in tr.find_all(
                    ["td", "th"], recursive=False
                )
            ]

            if len(cells) < 2:
                continue

            title = cells[0]

            match = re.search(
                r"\b(10Y|10-Year|10 Year)\b",
                title,
                re.I,
            )

            if not match:
                continue

            diagnostics["10-year candidate rows"] += 1

            country = normal_country(
                re.sub(
                    r"\s*(10Y|10-Year|10 Year).*$",
                    "",
                    title,
                    flags=re.I,
                )
            )

            # Last/yield is normally the first numeric
            # column after the bond name.
            value = parse_num(cells[1])

            if country and value is not None:
                if -5 < value < 100:
                    yields[country] = value

        # Second attempt: parse conventional HTML tables.
        if not yields:
            try:
                tables = pd.read_html(
                    io.StringIO(response.text),
                    flavor="lxml",
                )
            except (ValueError, ImportError):
                tables = []

            for table in tables:
                columns = [
                    str(c).lower()
                    for c in table.columns
                ]

                name_idx = next(
                    (i for i, c in enumerate(columns)
                     if "country" in c or "bond" in c),
                    None,
                )

                yield_idx = next(
                    (i for i, c in enumerate(columns)
                     if "yield" in c or c == "last"),
                    None,
                )

                if name_idx is None or yield_idx is None:
                    continue

                for _, row in table.iterrows():
                    title = str(row.iloc[name_idx])

                    if not re.search(
                        r"\b(10Y|10-Year|10 Year)\b",
                        title, re.I
                    ):
                        continue

                    country = normal_country(
                        re.sub(
                            r"\s*(10Y|10-Year|10 Year).*$",
                            "",
                            title,
                            flags=re.I,
                        )
                    )

                    value = parse_num(
                        row.iloc[yield_idx]
                    )

                    if country and value is not None:
                        if -5 < value < 100:
                            yields[country] = value

        if not yields:
            diagnostics["Error"] = (
                "Trading Economics returned no accessible "
                "10-year government bond yield rows."
            )

    except requests.exceptions.RequestException as exc:
        diagnostics["Error"] = str(exc)

    except Exception as exc:
        diagnostics["Error"] = (
            f"{type(exc).__name__}: {exc}"
        )

    return yields, diagnostics


# --------------------------------------------------
# LOAD AND REFRESH DATA
# --------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def load_data():
    data = {}
    errors = {}
    times = {}
    diagnostics = {}

    sources = [
        ("betas", get_betas),
        ("spread", get_spread),
        ("taxes", get_oecd_taxes),
    ]

    for key, function in sources:
        try:
            data[key] = function()
            times[key] = datetime.now(
                timezone.utc
            ).strftime("%Y-%m-%d %H:%M UTC")

        except Exception as exc:
            errors[key] = str(exc)

    yields, diagnostics = get_te_yields()

    if yields:
        data["yields"] = yields
        times["yields"] = datetime.now(
            timezone.utc
        ).strftime("%Y-%m-%d %H:%M UTC")
    else:
        errors["yields"] = (
            diagnostics.get("Error")
            or "No accessible yields returned"
        )

    return data, errors, times, diagnostics


# --------------------------------------------------
# PROFESSOR'S FINANCIAL FORMULAS
# --------------------------------------------------

def calculate(
    beta_u,
    tax,
    debt,
    erp,
    rf_us,
    rf_foreign,
    spread_us,
    spread_foreign=None,
):
    t = tax / 100
    d = debt
    premium = erp / 100
    us = rf_us / 100
    foreign = rf_foreign / 100
    spread = spread_us / 100

    if not 0 <= d < 1:
        raise ValueError("Debt share must be below 100%")

    factor = (1 + foreign) / (1 + us)

    beta_e = beta_u * (
        1 + (1 - t) * d / (1 - d)
    )

    eq_us = us + beta_e * premium
    debt_us = us + spread

    eq_foreign = (1 + eq_us) * factor - 1

    auto_spread = spread * factor

    spread_f = (
        auto_spread
        if spread_foreign is None
        else spread_foreign / 100
    )

    debt_foreign = foreign + spread_f

    wacc_us = (
        (1 - d) * eq_us
        + d * debt_us * (1 - t)
    )

    wacc_foreign = (
        (1 - d) * eq_foreign
        + d * debt_foreign * (1 - t)
    )

    return {
        "beta_e": beta_e,
        "eq_us": 100 * eq_us,
        "eq_foreign": 100 * eq_foreign,
        "debt_us": 100 * debt_us,
        "debt_foreign": 100 * debt_foreign,
        "wacc_us": 100 * wacc_us,
        "wacc_foreign": 100 * wacc_foreign,
        "auto_spread": 100 * auto_spread,
        "spread_foreign": 100 * spread_f,
        "after_us": 100 * debt_us * (1 - t),
        "after_foreign": 100 * debt_foreign * (1 - t),
    }


# --------------------------------------------------
# STREAMLIT INTERFACE
# --------------------------------------------------

st.title("🌍 International Cost of Capital")
st.caption(
    "Compare project financing in USD and local currency"
)

if st.button("🔄 Refresh all source data"):
    load_data.clear()
    st.rerun()

with st.spinner("Retrieving source data..."):
    data, errors, times, diagnostics = load_data()

st.info(
    "OECD tax rates use the uploaded OECD 2024 Excel "
    "workbook. Refresh rereads the workbook; it does "
    "not download newer OECD observations."
)

for key, error in errors.items():
    st.warning(
        f"{key.title()} source unavailable: {error}. "
        "Manual inputs or dated classroom references "
        "may be used."
    )

# --------------------------------------------------
# TRADING ECONOMICS DIAGNOSTIC PANEL
# --------------------------------------------------

with st.expander(
    "🔍 Trading Economics connection diagnostic",
    expanded="yields" in errors,
):
    st.write(
        "This panel shows what Trading Economics "
        "returned to the Streamlit server."
    )

    diagnostic_rows = [
        {"Check": key, "Result": str(value)}
        for key, value in diagnostics.items()
        if key != "Response preview"
    ]

    st.dataframe(
        pd.DataFrame(diagnostic_rows),
        hide_index=True,
        use_container_width=True,
    )

    if diagnostics.get("Response preview"):
        st.markdown("**First 1,500 characters of response:**")
        st.code(
            diagnostics["Response preview"],
            language="html",
        )

    if data.get("yields"):
        st.success(
            f"Extracted {len(data['yields'])} yields "
            "from Trading Economics."
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {"Country": k, "10Y yield (%)": v}
                    for k, v in sorted(
                        data["yields"].items()
                    )
                ]
            ),
            hide_index=True,
        )
    else:
        st.warning(
            "No live yields extracted. This diagnostic "
            "will help identify whether the page is "
            "blocked or the HTML structure has changed."
        )


# --------------------------------------------------
# PROJECT SETTINGS
# --------------------------------------------------

industries = data.get(
    "betas",
    pd.DataFrame({
        "Industry": ["Software (System & Application)"],
        "Unlevered beta": [np.nan],
    }),
)

industry_names = industries["Industry"].tolist()

default_ind = next(
    (
        i for i, name in enumerate(industry_names)
        if "software" in name.lower()
        and (
            "system" in name.lower()
            or "application" in name.lower()
        )
    ),
    0,
)

country_set = (
    set(CLASS_TAX_2026)
    | set(CLASS_YIELDS_NOV6)
    | set(data.get("taxes", {}))
    | set(data.get("yields", {}))
)

country_names = (
    ["United States"]
    + sorted(country_set - {"United States"})
)

with st.sidebar:
    st.header("Project settings")

    industry = st.selectbox(
        "Industry",
        industry_names,
        index=default_ind,
    )

    country = st.selectbox(
        "Target country",
        country_names,
        index=0,
    )

    erp = st.slider(
        "Equity risk premium (%)",
        0.0, 15.0, 6.5, 0.1,
    )

    debt = st.slider(
        "Target debt financing (%)",
        0, 95, 30, 1,
    ) / 100

    tax_choice = st.radio(
        "Project corporate tax rate",
        ["United States", "Selected country"],
        horizontal=True,
    )

    st.caption(
        "The selected tax rate applies to both "
        "financing currencies."
    )

    st.divider()
    st.header("Manual overrides")

    beta_auto = float(
        industries.loc[
            industries["Industry"] == industry,
            "Unlevered beta",
        ].iloc[0]
    )

    beta_manual = st.checkbox(
        "Override unlevered beta",
        value=not np.isfinite(beta_auto),
    )

    beta = st.number_input(
        "Unlevered beta",
        min_value=0.0,
        max_value=10.0,
        value=(
            beta_auto
            if np.isfinite(beta_auto)
            else 1.0
        ),
        step=0.01,
        disabled=not beta_manual,
    )

    if not beta_manual:
        beta = beta_auto

    tax_country = (
        "United States"
        if tax_choice == "United States"
        else country
    )

    tax_live = data.get("taxes", {}).get(tax_country)
    tax_ref = CLASS_TAX_2026.get(tax_country)

    tax_default = (
        tax_live
        if tax_live is not None
        else (
            tax_ref
            if tax_ref is not None
            else 25.0
        )
    )

    if tax_live is None:
        st.info(
            f"OECD Excel rate unavailable for {tax_country}. "
            "A classroom reference or editable placeholder "
            "is shown."
        )

    tax_manual = st.checkbox(
        "Override corporate tax rate",
        value=tax_live is None,
    )

    tax = st.number_input(
        "Corporate tax rate (%)",
        min_value=0.0,
        max_value=70.0,
        value=float(tax_default),
        step=0.1,
        disabled=not tax_manual,
    )

    if not tax_manual:
        tax = tax_default

    spread_result = data.get("spread")
    spread_live = (
        spread_result[0]
        if spread_result is not None
        else None
    )

    spread_manual = st.checkbox(
        "Override USD BBB spread",
        value=spread_live is None,
    )

    spread_us = st.number_input(
        "USD BBB spread (percentage points)",
        min_value=0.0,
        max_value=20.0,
        value=float(
            spread_live
            if spread_live is not None
            else 1.5
        ),
        step=0.05,
        disabled=not spread_manual,
    )

    if not spread_manual:
        spread_us = spread_live

    yields = data.get("yields", {})

    def yield_input(label, name):
        live = yields.get(name)
        reference = CLASS_YIELDS_NOV6.get(name)

        if live is None:
            st.info(
                f"{name}: live Trading Economics yield "
                "unavailable. Classroom reference is dated "
                "November 6, 2026, where available."
            )

        override = st.checkbox(
            f"Override {label} 10-year yield",
            value=live is None,
            key=f"override_{label}",
        )

        initial = (
            live
            if live is not None
            else (
                reference
                if reference is not None
                else 4.0
            )
        )

        value = st.number_input(
            f"{label} 10-year yield (%)",
            min_value=-5.0,
            max_value=100.0,
            value=float(initial),
            step=0.05,
            disabled=not override,
            key=f"yield_{label}",
        )

        return value if override else live

    rf_us = yield_input(
        "USD", "United States"
    )

    rf_foreign = (
        yield_input("Local", country)
        if country != "United States"
        else rf_us
    )

    foreign_override = st.checkbox(
        "Override local-currency BBB spread",
        value=False,
    )

    manual_foreign = st.number_input(
        "Local BBB spread (percentage points)",
        min_value=0.0,
        max_value=30.0,
        value=float(spread_us),
        step=0.05,
        disabled=not foreign_override,
    )


# --------------------------------------------------
# RESULTS
# --------------------------------------------------

if not np.isfinite(beta):
    st.error(
        "Industry beta unavailable. "
        "Enable the manual beta override."
    )
    st.stop()

res = calculate(
    beta,
    tax,
    debt,
    erp,
    rf_us,
    rf_foreign,
    spread_us,
    manual_foreign if foreign_override else None,
)

if country == "United States" and foreign_override:
    st.info(
        "For USD versus USD, disable the local spread "
        "override to keep both financing columns identical."
    )

st.subheader(
    f"Financing comparison · United States vs. {country}"
)

left, right = st.columns(2)

with left:
    st.markdown("### 🇺🇸 USD financing")
    st.metric("WACC", f"{res['wacc_us']:.2f}%")
    st.metric(
        "Cost of equity",
        f"{res['eq_us']:.2f}%",
    )
    st.metric(
        "Pretax cost of debt",
        f"{res['debt_us']:.2f}%",
    )

with right:
    st.markdown(f"### {country} · local currency")
    st.metric(
        "WACC",
        f"{res['wacc_foreign']:.2f}%",
    )
    st.metric(
        "Cost of equity",
        f"{res['eq_foreign']:.2f}%",
    )
    st.metric(
        "Pretax cost of debt",
        f"{res['debt_foreign']:.2f}%",
    )

comparison = pd.DataFrame(
    [
        (
            "Government 10-year yield",
            rf_us, rf_foreign,
        ),
        (
            "Cost of equity",
            res["eq_us"], res["eq_foreign"],
        ),
        (
            "Pretax cost of debt",
            res["debt_us"], res["debt_foreign"],
        ),
        (
            "After-tax cost of debt",
            res["after_us"], res["after_foreign"],
        ),
        (
            "WACC",
            res["wacc_us"], res["wacc_foreign"],
        ),
    ],
    columns=[
        "Metric",
        "USD (%)",
        f"{country} (%)",
    ],
)

st.dataframe(
    comparison,
    hide_index=True,
    use_container_width=True,
)

st.caption(
    f"Unlevered beta: {beta:.4f} | "
    f"Relevered beta: {res['beta_e']:.4f} | "
    f"Tax: {tax:.2f}% | "
    f"ERP: {erp:.2f}% | "
    f"Debt share: {debt:.0%} | "
    f"USD BBB spread: {spread_us:.4f} pp | "
    f"Local BBB spread: {res['spread_foreign']:.4f} pp"
)

with st.expander(
    "Calculation methodology and assumptions",
    expanded=True,
):
    st.markdown(
        r"""
**Relevered equity beta**

$$
\beta_E=\beta_U\left[1+(1-\tau)\frac{d}{1-d}\right]
$$

**USD cost of equity**

$$
R_{e,USD}=R_{f,USD}+\beta_E ERP
$$

**USD cost of debt**

$$
R_{d,USD}=R_{f,USD}+s_{USD}
$$

**Foreign cost of equity**

$$
1+R_{e,local}=(1+R_{e,USD})
\frac{1+R_{f,local}}{1+R_{f,USD}}
$$

**Automatic foreign BBB spread**

$$
s_{local}=s_{USD}
\frac{1+R_{f,local}}{1+R_{f,USD}}
$$

**Foreign cost of debt**

$$
R_{d,local}=R_{f,local}+s_{local}
$$

**WACC**

$$
WACC=(1-d)R_e+dR_d(1-\tau)
$$
"""
    )

    st.write(
        "Government bond yields proxy for currency-specific "
        "risk-free rates. Both scenarios use the same tax "
        "rate, debt share, and equity risk premium. "
        "The model assumes zero debt beta and usable "
        "interest tax shields."
    )

    st.write(
        "Discount cash flows using a WACC denominated "
        "in the same currency as those cash flows."
    )


# --------------------------------------------------
# ALL-INDUSTRY COMPARISON
# --------------------------------------------------

st.subheader("All-industry comparison")

all_rows = []

for _, row in industries.iterrows():
    b = row["Unlevered beta"]

    if pd.isna(b):
        continue

    z = calculate(
        float(b),
        tax,
        debt,
        erp,
        rf_us,
        rf_foreign,
        spread_us,
        manual_foreign if foreign_override else None,
    )

    all_rows.append({
        "Industry": row["Industry"],
        "Unlevered beta": b,
        "Relevered beta": z["beta_e"],
        "USD equity (%)": z["eq_us"],
        "Local equity (%)": z["eq_foreign"],
        "USD debt (%)": z["debt_us"],
        "Local debt (%)": z["debt_foreign"],
        "USD WACC (%)": z["wacc_us"],
        "Local WACC (%)": z["wacc_foreign"],
    })

all_df = pd.DataFrame(all_rows)

if not all_df.empty:
    st.dataframe(
        all_df,
        hide_index=True,
        use_container_width=True,
    )

    st.download_button(
        "⬇️ Download all industries (CSV)",
        all_df.to_csv(index=False).encode(),
        "all_industry_cost_of_capital.csv",
        "text/csv",
    )

st.download_button(
    "⬇️ Download selected project (CSV)",
    comparison.to_csv(index=False).encode(),
    "selected_project_cost_of_capital.csv",
    "text/csv",
)


# --------------------------------------------------
# SOURCE TRANSPARENCY
# --------------------------------------------------

st.subheader("Source transparency")

source_rows = []

sources = [
    ("betas", BETA_URL),
    ("spread", SPREAD_URL),
    (
        "taxes",
        "OECD Corporate Tax Statistics 2024 — "
        "uploaded Excel, Figure 2.1",
    ),
    ("yields", TE_URL),
]

for key, source in sources:
    source_rows.append({
        "Dataset": key,
        "Source": source,
        "Retrieved (UTC)": times.get(
            key, "Unavailable"
        ),
        "Status": (
            "Loaded"
            if key in data
            else "Unavailable — manual/reference required"
        ),
    })

st.dataframe(
    pd.DataFrame(source_rows),
    hide_index=True,
    use_container_width=True,
)

st.caption(
    "OECD Excel observations are from 2024. "
    "Classroom tax references are from 2026, and "
    "classroom bond yields are dated November 6, 2026. "
    "Retrieval timestamps do not represent market "
    "observation dates. Verify current source values "
    "before relying on the results."
)

if spread_result:
    st.caption(
        "BBB parser note: " + spread_result[1]
    )
