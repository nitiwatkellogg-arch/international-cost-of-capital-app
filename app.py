"""International Cost of Capital | Kellogg International Finance."""
import io
from pathlib import Path
import re
from datetime import datetime, timezone
from urllib.parse import urljoin
import numpy as np
import pandas as pd
import requests
import streamlit as st
import pycountry
from bs4 import BeautifulSoup

st.set_page_config(page_title="International Cost of Capital", page_icon="🌍", layout="wide")
BETA_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls"
SPREAD_URL = "https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ratings.html"
OECD_URL = "https://www.oecd.org/en/publications/corporate-tax-statistics-2024_9c27d6e8-en/full-report/statutory-corporate-income-tax-rates_440f9286.html#chapter-d1e2342-08e74a33fb"
TE_URL = "https://tradingeconomics.com/bonds"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AcademicResearch/1.0)"}
# Reference values are explicitly dated classroom examples, NEVER silently treated as current data.
CLASS_TAX_2026 = {"United States":25.5,"Canada":26.0,"Mexico":30.0,"United Kingdom":25.0,"Germany":30.1,"France":36.1,"Japan":29.7,"China":25.0,"India":25.2,"Australia":30.0,"Brazil":34.0,"Colombia":35.0,"Thailand":20.0,"Singapore":17.0,"Indonesia":22.0,"Vietnam":20.0,"Malaysia":24.0,"Philippines":25.0,"South Korea":27.5,"Switzerland":19.5,"Ireland":12.5,"Italy":27.8,"Spain":25.0,"Netherlands":25.8,"Sweden":20.6,"Norway":22.0,"Denmark":22.0,"Poland":19.0,"Portugal":29.5,"New Zealand":28.0,"Chile":27.0,"Peru":29.5,"South Africa":27.0,"Turkey":25.0,"Argentina":35.0,"Belgium":25.0,"Austria":23.0,"Finland":20.0,"Greece":22.0,"Israel":23.0,"Czech Republic":21.0,"Hungary":9.0,"United Arab Emirates":9.0}
CLASS_YIELDS_NOV6 = {"United States":4.9,"Brazil":15.2,"Colombia":12.8,"Mexico":9.1,"India":7.2,"Poland":6.2,"United Kingdom":5.2,"Australia":5.0,"France":4.8,"Slovakia":4.2,"Portugal":3.7,"Canada":3.7,"Germany":3.3,"Japan":2.6,"China":1.6,"Switzerland":0.4}
ALIASES={"US":"United States","USA":"United States","UK":"United Kingdom","Britain":"United Kingdom","South Korea":"South Korea","Korea":"South Korea","Czechia":"Czech Republic","Türkiye":"Turkey","Turkiye":"Turkey","UAE":"United Arab Emirates","Viet Nam":"Vietnam","Russian Federation":"Russia"}

def fetch(url, timeout=22):
    r=requests.get(url,headers=HEADERS,timeout=timeout);r.raise_for_status();return r

def normal_country(s):
    s=re.sub(r"\s+"," ",str(s)).strip();return ALIASES.get(s,s)

def parse_num(x):
    if pd.isna(x):return None
    s=str(x).replace(",","").replace("%","").strip()
    m=re.search(r"-?\d+(?:\.\d+)?",s)
    return float(m.group()) if m else None

def get_betas():
    content=fetch(BETA_URL).content
    book=pd.ExcelFile(io.BytesIO(content))
    for sheet in book.sheet_names:
        raw=pd.read_excel(io.BytesIO(content),sheet_name=sheet,header=None)
        for i in range(min(18,len(raw))):
            header=[str(v).strip().lower() for v in raw.iloc[i]]
            ind=next((j for j,v in enumerate(header) if 'industry name' in v or v=='industry'),None)
            beta=next((j for j,v in enumerate(header) if 'unlevered beta' in v and 'cash' not in v and 'corrected' not in v),None)
            if ind is not None and beta is not None:
                out=raw.iloc[i+1:,[ind,beta]].copy();out.columns=['Industry','Unlevered beta']
                out['Unlevered beta']=pd.to_numeric(out['Unlevered beta'],errors='coerce')
                out=out.dropna();out['Industry']=out['Industry'].astype(str).str.strip()
                out=out[(out['Unlevered beta']>=0)&(out['Unlevered beta']<10)&(~out['Industry'].str.contains('total market',case=False))]
                if len(out)>10:return out.drop_duplicates('Industry').sort_values('Industry').reset_index(drop=True)
    raise ValueError('Could not identify industry and unlevered-beta columns in Damodaran workbook')

def get_spread():
    html=fetch(SPREAD_URL).text
    tables=pd.read_html(io.StringIO(html),flavor="lxml")
    for t in tables:
        for _,row in t.iterrows():
            cells=[str(v).strip() for v in row]
            if any(re.search(r'\b(Baa2|BBB)\b',c,re.I) for c in cells):
                nums=[parse_num(c) for c in cells]
                # Damodaran ratings page often has columns: rating, interest coverage, spread (large), spread (small)
                candidates=[(j,n) for j,n in enumerate(nums) if n is not None and '%' in cells[j]]
                if candidates:
                    return candidates[0][1], 'Percent from first spread column for Baa2/BBB (verify large non-financial column)'
                # No percent signs: identify column by header, not arbitrary numeric position.
                columns=[str(c).lower() for c in t.columns]
                spreadcols=[j for j,c in enumerate(columns) if 'spread' in c]
                if spreadcols:
                    v=nums[spreadcols[0]]
                    if v is not None:return v,'Spread column for Baa2/BBB'
    raise ValueError('BBB large-firm spread could not be safely extracted; enter it manually')

def get_te_yields():
    """Read the assigned Trading Economics bonds webpage, without a second provider."""
    html = fetch(TE_URL).text
    soup = BeautifulSoup(html, 'lxml')
    result = {}
    # Trading Economics may supply table rows without a conventional <table>.
    for tr in soup.select('tr'):
        cells = [c.get_text(' ', strip=True) for c in tr.find_all(['td', 'th'], recursive=False)]
        if len(cells) < 2:
            continue
        title = cells[0]
        if not re.search(r'\b(10Y|10-Year|10 Year)\b', title, re.I):
            continue
        country = normal_country(re.sub(r'\s*(10Y|10-Year|10 Year).*$', '', title, flags=re.I))
        # Yield/Last is usually the first numeric column after the bond name.
        value = parse_num(cells[1])
        if country and value is not None and -5 < value < 100:
            result[country] = value
    if result:
        return result
    # Fallback to HTML tables if the provider restores conventional markup.
    try:
        tables = pd.read_html(io.StringIO(html), flavor='lxml')
    except (ValueError, ImportError):
        tables = []
    for table in tables:
        columns = [str(c).lower() for c in table.columns]
        name_idx = next((i for i, c in enumerate(columns) if 'country' in c or 'bond' in c), None)
        yield_idx = next((i for i, c in enumerate(columns) if c in ('yield', 'last') or 'yield' in c), None)
        if name_idx is None or yield_idx is None:
            continue
        for _, row in table.iterrows():
            label = str(row.iloc[name_idx])
            if not re.search(r'\b(10Y|10-Year|10 Year)\b', label, re.I):
                continue
            name = normal_country(re.sub(r'\s*(10Y|10-Year|10 Year).*$', '', label, flags=re.I))
            value = parse_num(row.iloc[yield_idx])
            if name and value is not None and -5 < value < 100:
                result[name] = value
    if not result:
        raise ValueError('The assigned Trading Economics page did not provide accessible 10-year yield rows. Enter yields manually; no other data source was used')
    return result

def get_oecd_taxes():
    """Read the user-provided OECD 2024 Figure 2.1 Excel workbook (not live data)."""
    path = Path(__file__).resolve().parent / "oecd_corporate_tax_2024.xlsx"
    if not path.exists():
        raise FileNotFoundError("Upload oecd_corporate_tax_2024.xlsx to the GitHub repository root")
    raw = pd.read_excel(path, sheet_name="g2_1", header=None)
    result = {}
    for code, value in raw.iloc[:, :2].itertuples(index=False, name=None):
        if not isinstance(code, str) or not re.fullmatch(r"[A-Z]{3}", code):
            continue
        if not isinstance(value, (int, float, np.number)) or pd.isna(value):
            continue
        try:
            country = pycountry.countries.get(alpha_3=code)
            if country is None:
                continue
            name = normal_country(country.name)
            name = {"Korea, Republic of": "South Korea", "Viet Nam": "Vietnam",
                    "Türkiye": "Turkey", "Czechia": "Czech Republic",
                    "United Arab Emirates": "United Arab Emirates"}.get(name, name)
            result[name] = float(value) * 100  # OECD workbook stores rates as fractions
        except (TypeError, ValueError):
            continue
    if not result:
        raise ValueError("No ISO3 corporate tax rates found in the supplied OECD workbook")
    return result

@st.cache_data(ttl=3600,show_spinner=False)
def load_data():
    output={};errors={};times={}
    for key,fn in [('betas',get_betas),('spread',get_spread),('taxes',get_oecd_taxes),('yields',get_te_yields)]:
        try:
            output[key]=fn();times[key]=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        except Exception as e:errors[key]=str(e)
    return output,errors,times

def calculate(beta_u, tax, debt, erp, rf_us, rf_foreign, spread_us, spread_foreign=None):
    """All inputs except beta_u and debt are in percentage points."""
    t=tax/100; d=debt; premium=erp/100; us=rf_us/100; foreign=rf_foreign/100; s=spread_us/100
    if not 0<=d<1:raise ValueError('Debt share must be below 100%')
    factor=(1+foreign)/(1+us)
    beta_e=beta_u*(1+(1-t)*d/(1-d))
    eq_us=us+beta_e*premium
    debt_us=us+s
    eq_foreign=(1+eq_us)*factor-1
    auto_spread=s*factor
    spread_f=auto_spread if spread_foreign is None else spread_foreign/100
    debt_foreign=foreign+spread_f
    wacc_us=(1-d)*eq_us+d*debt_us*(1-t)
    wacc_foreign=(1-d)*eq_foreign+d*debt_foreign*(1-t)
    return dict(beta_e=beta_e,eq_us=100*eq_us,eq_foreign=100*eq_foreign,debt_us=100*debt_us,debt_foreign=100*debt_foreign,wacc_us=100*wacc_us,wacc_foreign=100*wacc_foreign,auto_spread=100*auto_spread,spread_foreign=100*spread_f,after_us=100*debt_us*(1-t),after_foreign=100*debt_foreign*(1-t),factor=factor)

st.title('🌍 International Cost of Capital')
st.caption('Compare USD and local-currency cost of equity, debt, and WACC | Classroom valuation model')
if st.button('🔄 Refresh all source data'):
    load_data.clear();st.rerun()
with st.spinner('Retrieving public source data…'):
    data,errors,times=load_data()
st.info('OECD statutory tax rates: uploaded OECD Corporate Tax Statistics 2024, Figure 2.1 (2024 observations). The refresh button rereads this bundled workbook; it does not download new OECD data. For newer rates, replace the workbook with an updated OECD file in the same layout.')
for k,err in errors.items():st.warning(f'{k.title()} source unavailable: {err}. Enter a manual value or use the explicitly dated classroom reference where offered.')

industries=data.get('betas',pd.DataFrame({'Industry':['Software (System & Application)'],'Unlevered beta':[np.nan]}))
industry_names=industries['Industry'].tolist()
default_ind=next((i for i,n in enumerate(industry_names) if 'software' in n.lower() and ('system' in n.lower() or 'application' in n.lower())),0)
country_set=set(CLASS_TAX_2026)|set(CLASS_YIELDS_NOV6)|set(data.get('yields',{}))|set(data.get('taxes',{}))
country_names=['United States']+sorted(country_set-{'United States'})
with st.sidebar:
    st.header('Project settings')
    industry=st.selectbox('Industry',industry_names,index=default_ind)
    country=st.selectbox('Target country',country_names,index=0)
    erp=st.slider('Equity risk premium (%)',0.0,15.0,6.5,0.1)
    debt=st.slider('Target debt financing (%)',0,95,30,1)/100
    tax_choice=st.radio('Project corporate tax rate', ['United States','Selected country'],horizontal=True)
    st.caption('The chosen project tax rate applies to BOTH financing currencies.')
    st.divider()
    st.header('Manual overrides')
    beta_auto=float(industries.loc[industries['Industry']==industry,'Unlevered beta'].iloc[0])
    beta_manual=st.checkbox('Override unlevered beta')
    beta=st.number_input('Unlevered beta',min_value=0.0,max_value=10.0,value=beta_auto if np.isfinite(beta_auto) else 1.0,step=0.01,disabled=not beta_manual)
    if not beta_manual:beta=beta_auto
    tax_country='United States' if tax_choice=='United States' else country
    tax_live=data.get('taxes',{}).get(tax_country)
    tax_ref=CLASS_TAX_2026.get(tax_country)
    if tax_live is None:
        st.info(f'OECD current tax for {tax_country} not verified. Classroom 2026 reference shown; confirm before using.')
    tax_manual=st.checkbox('Override corporate tax rate',value=(tax_live is None))
    tax_default=tax_live if tax_live is not None else (tax_ref if tax_ref is not None else 25.0)
    tax=st.number_input('Corporate tax rate (%)',0.0,70.0,float(tax_default),0.1,disabled=not tax_manual)
    if not tax_manual:tax=tax_default
    spread_result=data.get('spread')
    spread_live=spread_result[0] if spread_result else None
    spread_manual=st.checkbox('Override USD BBB spread',value=spread_live is None)
    spread_us=st.number_input('USD BBB spread (percentage points)',0.0,20.0,float(spread_live if spread_live is not None else 1.5),0.05,disabled=not spread_manual)
    if not spread_manual:spread_us=spread_live
    yields=data.get('yields',{})
    def yield_input(label,name):
        live=yields.get(name)
        reference=CLASS_YIELDS_NOV6.get(name)
        if live is None:st.info(f'{name} live yield unavailable; reference dated Nov 6, 2026 where available.')
        override=st.checkbox(f'Override {label} 10-year yield',value=live is None,key=f'override_{label}')
        initial=live if live is not None else (reference if reference is not None else 4.0)
        val=st.number_input(f'{label} 10-year yield (%)',-5.0,100.0,float(initial),0.05,disabled=not override,key=f'yield_{label}')
        return val if override else live
    rf_us=yield_input('USD','United States')
    rf_foreign=yield_input('Local',country) if country!='United States' else rf_us
    foreign_override=st.checkbox('Override local-currency BBB spread',value=False)
    manual_foreign=st.number_input('Local BBB spread (percentage points)',0.0,30.0,float(spread_us),0.05,disabled=not foreign_override)

if not np.isfinite(beta):st.error('Industry beta unavailable: enable its manual override.');st.stop()
res=calculate(beta,tax,debt,erp,rf_us,rf_foreign,spread_us,manual_foreign if foreign_override else None)
if country=='United States' and foreign_override:st.info('For a USD-to-USD comparison, disable the local spread override to keep both columns identical.')
st.subheader(f'Financing comparison · United States vs. {country}')
left,right=st.columns(2)
with left:
    st.markdown('### 🇺🇸 USD financing')
    st.metric('WACC',f"{res['wacc_us']:.2f}%")
    st.metric('Cost of equity',f"{res['eq_us']:.2f}%")
    st.metric('Pretax cost of debt',f"{res['debt_us']:.2f}%")
with right:
    st.markdown(f'### {country} · local currency')
    st.metric('WACC',f"{res['wacc_foreign']:.2f}%")
    st.metric('Cost of equity',f"{res['eq_foreign']:.2f}%")
    st.metric('Pretax cost of debt',f"{res['debt_foreign']:.2f}%")
rows=[('Government 10-year yield',rf_us,rf_foreign),('Cost of equity',res['eq_us'],res['eq_foreign']),('Pretax cost of debt',res['debt_us'],res['debt_foreign']),('After-tax cost of debt',res['after_us'],res['after_foreign']),('WACC',res['wacc_us'],res['wacc_foreign'])]
comparison=pd.DataFrame(rows,columns=['Metric','USD (%)',f'{country} (%)'])
st.dataframe(comparison.style.format({'USD (%)':'{:.4f}',f'{country} (%)':'{:.4f}'}),hide_index=True,use_container_width=True)
st.caption(f"Unlevered beta {beta:.4f} → relevered beta {res['beta_e']:.4f}; project tax {tax:.2f}%; ERP {erp:.2f}%; debt {debt:.0%}; USD BBB spread {spread_us:.4f} pp; local BBB spread {res['spread_foreign']:.4f} pp ({'manual' if foreign_override else 'automatic'}).")
with st.expander('Calculation methodology and assumptions',expanded=True):
    st.markdown(r'''**Relevered equity beta:** $\beta_E=\beta_U[1+(1-\tau)d/(1-d)]$  
**USD equity:** $R_{e,USD}=R_{f,USD}+\beta_E\,ERP$  
**USD debt:** $R_{d,USD}=R_{f,USD}+s_{USD}$  
**Currency conversion:** $1+R_{e,local}=(1+R_{e,USD})(1+R_{f,local})/(1+R_{f,USD})$  
**Automatic local BBB spread:** $s_{local}=s_{USD}(1+R_{f,local})/(1+R_{f,USD})$  
**Local debt:** $R_{d,local}=R_{f,local}+s_{local}$ (unless manually overridden)  
**Both WACCs:** $WACC=(1-d)R_e+dR_d(1-\tau)$''')
    st.write('10-year government yields are proxies for currency-specific risk-free rates, not necessarily default-free yields. The model assumes zero debt beta, fully usable interest tax shields, a common project tax rate, and no separate country equity risk premium. The foreign BBB spread can be manually set, breaking exact currency-conversion consistency for debt and WACC.')
    st.write('Compare each WACC only against cash flows denominated in its respective currency. Rates are nominal annual percentages.')

st.subheader('All-industry comparison')
all_rows=[]
for _,r in industries.iterrows():
    b=r['Unlevered beta']
    if pd.isna(b):continue
    z=calculate(float(b),tax,debt,erp,rf_us,rf_foreign,spread_us,manual_foreign if foreign_override else None)
    all_rows.append({'Industry':r['Industry'],'Unlevered beta':b,'Relevered beta':z['beta_e'],'USD equity (%)':z['eq_us'],'Local equity (%)':z['eq_foreign'],'USD debt (%)':z['debt_us'],'Local debt (%)':z['debt_foreign'],'USD WACC (%)':z['wacc_us'],'Local WACC (%)':z['wacc_foreign']})
all_df=pd.DataFrame(all_rows)
if not all_df.empty:
    st.dataframe(all_df,use_container_width=True,hide_index=True)
    st.download_button('⬇️ Download all industries (CSV)',all_df.to_csv(index=False).encode(),'all_industry_cost_of_capital.csv','text/csv')
st.download_button('⬇️ Download selected project (CSV)',comparison.to_csv(index=False).encode(),'selected_project_cost_of_capital.csv','text/csv')

st.subheader('Source transparency')
source_rows=[]
for key,source in [('betas',BETA_URL),('spread',SPREAD_URL),('taxes','OECD Corporate Tax Statistics 2024 — bundled Excel, Figure 2.1'),('yields',TE_URL)]:
    source_rows.append({'Dataset':key,'Source':source,'Retrieval (UTC)':times.get(key,'Unavailable'),'Status':'Fetched / parsed' if key in data else 'Unavailable — manual/reference required'})
st.dataframe(pd.DataFrame(source_rows),hide_index=True,use_container_width=True)
st.caption('Tax source observation year: 2024 (bundled OECD Excel). Retrieval time is not the source observation date. Inspect the source for its published dataset date. Reference tax figures are from professor slides (OECD 2026); reference yields are from slides dated Nov 6, 2026. These references are not represented as live fetched data.')
if spread_result:st.caption('BBB parser note: '+spread_result[1])
