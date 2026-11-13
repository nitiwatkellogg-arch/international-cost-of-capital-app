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
    """Fetch only Trading Economics; preserve response for downloadable diagnosis."""
    diagnostics = {"HTTP status": "Not received", "Final URL": TE_URL,
                   "Response length": 0, "HTML table count": 0,
                   "HTML row count": 0, "10-year candidate rows": 0,
                   "Error": ""}
    html = ""
    result = {}
    try:
        response = requests.get(TE_URL, headers=HEADERS, timeout=30)
        html = response.text
        diagnostics["HTTP status"] = response.status_code
        diagnostics["Final URL"] = response.url
        diagnostics["Response length"] = len(html)
        response.raise_for_status()
        soup = BeautifulSoup(html, "lxml")
        diagnostics["HTML table count"] = len(soup.select("table"))
        diagnostics["HTML row count"] = len(soup.select("tr"))
        for tr in soup.select("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False)]
            if len(cells) < 2 or not re.search(r"\b(10Y|10-Year|10 Year)\b", cells[0], re.I):
                continue
            diagnostics["10-year candidate rows"] += 1
