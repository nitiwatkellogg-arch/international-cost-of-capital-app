# International Cost of Capital — Streamlit

Compare cost of equity, pretax/after-tax cost of debt, and WACC in USD and a selected country's currency, using the Kellogg International Finance class model.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy

1. Create a public GitHub repository named `international-cost-of-capital`.
2. Upload `app.py`, `requirements.txt`, and `README.md` to its root.
3. Visit https://share.streamlit.io/ → New app → select repository, branch `main`, entry point `app.py` → Deploy.
4. Test the default configuration, source refresh, foreign country, manual overrides, and CSV download.

## Formulas

- D/E = d/(1-d)
- Levered beta = unlevered beta × [1+(1-tax)×D/E]
- USD cost of equity = USD 10-year yield + levered beta × ERP
- USD pretax debt cost = USD 10-year yield + USD BBB spread
- Currency conversion factor = (1+local 10-year yield)/(1+USD 10-year yield)
- Local cost of equity = (1+USD cost of equity) × factor − 1
- Auto local BBB spread = USD BBB spread × factor
- Local debt cost = local 10-year yield + local BBB spread
- WACC = (1-debt share)×equity cost + debt share×debt cost×(1-tax)

All calculations use decimal rates internally, not percentage-point numbers.

## Verification — professor's Colombia example (slides 25–28)

Manually set: unlevered beta 0.80; debt 30%; tax 35%; ERP 6.5%; USD 10-year yield 4%; Colombia 10-year yield 12%; USD BBB spread 1.5 percentage points. Disable local spread override.

Expected results:

| Metric | USD | COP |
|---|---:|---:|
| Relevered beta | 1.022857 | 1.022857 |
| Equity cost | 10.6486% | 19.1600% |
| Pretax debt cost | 5.5000% | 13.6154% |
| After-tax debt cost | 3.5750% | 8.8500% |
| WACC | 8.5265% | 16.0670% |

When the target country is United States, with no foreign spread override, both currency columns should match exactly.

## Data reliability and limitations

- Damodaran industry unlevered betas: https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls
- Damodaran Baa2/BBB spread: https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ratings.html
- OECD statutory corporate rates: https://www.oecd.org/en/publications/corporate-tax-statistics-2024_9c27d6e8-en/full-report/statutory-corporate-income-tax-rates_440f9286.html
- Trading Economics government yields: https://tradingeconomics.com/bonds

Website HTML structures can change, and the OECD narrative page may not expose a machine-readable country table. The app shows fetch failures rather than inventing live values. Where live values cannot be verified, users must confirm/override the explicitly labeled classroom reference values. The class tax reference is dated 2026; the class yield reference is dated November 6, 2026. The initial USD BBB 1.5pp value is the **class example**, not a claim of the latest observed spread.

The government yield is a proxy for the risk-free rate and may contain sovereign credit risk. The model does not add a separate country equity risk premium, consistent with the class example. This app is educational and not investment advice.

## Data-source troubleshooting (November 2026 update)

- **OECD 403:** The app now calls the official OECD report webpage specified in the assignment (may block automated requests with HTTP 403).
- **Trading Economics / html5lib:** `html5lib` is now included in `requirements.txt`, and HTML table parsing explicitly uses `lxml`. Trading Economics can still change its HTML or block automated requests; if so, the app labels the source unavailable and allows manual values.
- Reboot/redeploy the Streamlit app after replacing `app.py` and `requirements.txt` in GitHub.


### OECD Excel tax source
The repository includes `oecd_corporate_tax_2024.xlsx`, the user-supplied OECD Corporate Tax Statistics 2024 Figure 2.1 workbook. Tax observations are **2024**, not live 2026 rates. `Refresh all source data` rereads the bundled file; replace it with a newer OECD workbook if required. The Trading Economics bond-yield fetch is unchanged and may still need manual inputs when blocked.
