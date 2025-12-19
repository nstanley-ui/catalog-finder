import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
from urllib.parse import urljoin

# --- CONFIGURATION ---
st.set_page_config(page_title="Universal Catalog Discoverer", page_icon="🕵️", layout="wide")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

# --- SMART FILTERS ---
# 1. POSITIVE MATCHES: The URL must contain one of these.
TARGET_KEYWORDS = [
    '/product/', '/products/', '/platform/',  # High Priority (User Request)
    '/solution/', '/software/', '/feature/', '/module/'   # Secondary B2B
]

# 2. NEGATIVE MATCHES: Ignore these pages.
BLACKLIST_KEYWORDS = [
    'career', 'job', 'hiring', 'apply',       # Recruiting
    'policy', 'privacy', 'terms', 'legal',    # Legal
    'blog', 'news', 'press', 'release',       # Content
    'login', 'signin', 'register', 'account', # Auth
    'about-us', 'contact', 'investor', 'faq', # Info
    'support', 'help', 'docs'                 # Support
]

def is_valid_url(url):
    """Returns True if it matches Targets and isn't in Blacklist"""
    url_lower = url.lower()
    
    # Must match at least one Target
    if not any(k in url_lower for k in TARGET_KEYWORDS):
        return False
        
    # Must NOT match any Blacklist
    for bad_word in BLACKLIST_KEYWORDS:
        if bad_word in url_lower:
            return False
            
    return True

def clean_domain(url):
    url = url.strip()
    if not url.startswith('http'):
        url = 'https://' + url
    return url.rstrip('/')

def clean_link(url):
    """Removes query params (?utm=...) and trailing slashes for deduplication"""
    if not url: return ""
    return url.split('?')[0].split('#')[0].rstrip('/')

def classify_type(url):
    """Categorizes the link based on the keyword found"""
    if '/platform' in url: return "Platform"
    if '/product' in url: return "Product"
    if '/solution' in url: return "Solution"
    return "Feature/Service"

# --- STRATEGIES ---

def strategy_shopify(domain):
    try:
        url = f"{domain}/products.json?limit=250"
        r = requests.get(url, headers=HEADERS, timeout=4)
        if r.status_code == 200:
            data = r.json()
            if 'products' in data and len(data['products']) > 0:
                return [{
                    "Name": p.get('title'),
                    "Type": "Product (Retail)",
                    "URL": f"{domain}/products/{p.get('handle')}",
                    "Method": "Shopify API"
                } for p in data['products']]
    except: pass
    return []

def strategy_nav_scan(domain):
    """Scans homepage navigation links"""
    try:
        r = requests.get(domain, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(r.text, 'html.parser')
        found_items = {}
        
        for a in soup.find_all('a', href=True):
            href = a.get('href')
            full_url = urljoin(domain, href)
            
            # CLEANING: Remove ?params and trailing /
            full_url = clean_link(full_url)
            
            # Filter Logic
            if domain not in full_url: continue
            if not is_valid_url(full_url): continue
            
            # Clean Title
            title = a.get_text(strip=True)
            if not title or len(title) > 60: 
                title = full_url.split('/')[-1].replace('-', ' ').title()
                
            if full_url not in found_items:
                found_items[full_url] = {
                    "Name": title,
                    "Type": classify_type(full_url),
                    "URL": full_url,
                    "Method": "Homepage Nav Scan"
                }
        return list(found_items.values())[:40]
    except: pass
    return []

def strategy_sitemap(domain):
    """Scans sitemap.xml"""
    try:
        sitemaps = [f"{domain}/sitemap.xml", f"{domain}/sitemap_index.xml", f"{domain}/wp-sitemap.xml"]
        for sm_url in sitemaps:
            try:
                r = requests.get(sm_url, headers=HEADERS, timeout=5)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.content, 'xml')
                    urls = [u.text for u in soup.find_all('loc')]
                    
                    found = []
                    for u in urls:
                        # CLEANING
                        u = clean_link(u)
                        
                        if is_valid_url(u):
                            found.append({
                                "Name": u.split('/')[-1].replace('-', ' ').title(),
                                "Type": classify_type(u),
                                "URL": u,
                                "Method": "Sitemap Scan"
                            })
                    if found: return found[:50]
            except: continue
    except: pass
    return []

# --- UI ---
st.title("🕵️ Universal Catalog Discoverer")
st.caption("Targeting: `/product/`, `/products/`, `/platform/` (ignoring careers/legal/blogs)")

col1, col2 = st.columns([3, 1])
with col1:
    domain_input = st.text_input("Company Domain", placeholder="e.g. 6sense.com")
with col2:
    st.write("")
    st.write("")
    run_btn = st.button("🚀 Find Catalog", type="primary", use_container_width=True)

if run_btn and domain_input:
    domain = clean_domain(domain_input)
    st.divider()
    
    with st.status(f"Scanning {domain}...", expanded=True) as status:
        st.write("Checking Shopify API...")
        results = strategy_shopify(domain)
        
        if not results:
            st.write("Scanning Homepage Links...")
            results = strategy_nav_scan(domain)
            
        if not results:
            st.write("Checking Sitemaps...")
            results = strategy_sitemap(domain)
            
        if results:
            status.update(label="✅ Catalog Found!", state="complete", expanded=False)
        else:
            status.update(label="❌ No data found.", state="error", expanded=False)

    if results:
        df = pd.DataFrame(results)
        st.dataframe(
            df, 
            column_config={"URL": st.column_config.LinkColumn("Link")}, 
            use_container_width=True,
            hide_index=True
        )
        
        # Clean filename for download
        clean_name = domain_input.replace('.', '_').replace('/', '')
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download CSV", csv, f"{clean_name}_catalog.csv", "text/csv")
    else:
        st.warning("No products found matching target paths.")
