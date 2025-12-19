import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urljoin, urlparse
import time

# --- CONFIGURATION ---
st.set_page_config(page_title="B2B Schema Discoverer", page_icon="🧩", layout="wide")

# Rotating headers to avoid lightweight blocking
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

# --- 1. SCHEMA DEFINITIONS ---
DIRECTORY_PATTERNS = {
    '/products/': 'Product Suite',
    '/product/': 'Product Suite',
    '/platform/': 'Platform Feature',       # 6sense
    '/solutions/': 'Solution (Use Case)',   # Demandbase
    '/features/': 'Platform Feature',
    '/software/': 'Product Suite',
    '/capabilities/': 'Platform Feature',
    '/module/': 'Platform Module'
}

FLAT_SCHEMA_KEYWORDS = [
    'advertising', 'marketing', 'intelligence', 'sales', 'revenue',
    'programmatic', 'dsp', 'campaign', 'channel', 'inventory',
    'native', 'display', 'video', 'audio', 'connected-tv', 'ctv',
    'abm', 'b2b', 'data', 'cloud', 'engine', 'studio'
]

BLACKLIST_KEYWORDS = [
    'career', 'job', 'hiring', 'apply', 'team', 'people',       # HR
    'policy', 'privacy', 'terms', 'legal', 'gdpr', 'security',  # Legal
    'blog', 'news', 'press', 'release', 'media', 'events',      # Content
    'login', 'signin', 'register', 'account', 'portal',         # Auth
    'about', 'contact', 'investor', 'faq', 'support', 'help',   # Info
    'customer', 'case-study', 'resource', 'ebook', 'webinar',   # Marketing
    'author', 'tag', 'category', 'archive'                      # WP Junk
]

def clean_link(url):
    if not url: return ""
    return url.split('?')[0].split('#')[0].rstrip('/')

def is_root_url(domain, url):
    path = url.replace(domain, '').strip('/')
    return '/' not in path and path != ''

def classify_schema(url, domain):
    for pattern, schema_name in DIRECTORY_PATTERNS.items():
        if pattern in url.lower():
            return schema_name
    if is_root_url(domain, url):
        return "Flat / Root (High Volume)"
    return "Other Product Page"

def is_valid_candidate(url, domain):
    url_lower = url.lower()
    if any(bad in url_lower for bad in BLACKLIST_KEYWORDS):
        return False
    if any(pattern in url_lower for pattern in DIRECTORY_PATTERNS.keys()):
        return True
    if is_root_url(domain, url):
        if any(kw in url_lower for kw in FLAT_SCHEMA_KEYWORDS):
            return True
    return False

# --- RECURSIVE SITEMAP LOGIC ---

def fetch_sitemap_urls(sitemap_url, domain, depth=0):
    """Recursively fetches URLs from sitemaps and sitemap indices"""
    if depth > 2: return [] # Prevent infinite loops
    
    found_pages = []
    try:
        r = requests.get(sitemap_url, headers=HEADERS, timeout=6)
        if r.status_code != 200: return []
        
        soup = BeautifulSoup(r.content, 'xml')
        
        # 1. Check for Nested Sitemaps (<sitemap><loc>...</loc></sitemap>)
        sitemap_tags = soup.find_all('sitemap')
        for sm in sitemap_tags:
            loc = sm.find('loc')
            if loc:
                child_url = loc.text.strip()
                # Only dive into relevant sitemaps (skip blog/author/category sitemaps)
                if any(x in child_url for x in ['page', 'product', 'solution', 'service']):
                    found_pages.extend(fetch_sitemap_urls(child_url, domain, depth+1))
        
        # 2. Check for Actual Pages (<url><loc>...</loc></url>)
        url_tags = soup.find_all('url')
        for url in url_tags:
            loc = url.find('loc')
            if loc:
                page_url = clean_link(loc.text.strip())
                if is_valid_candidate(page_url, domain):
                    title = page_url.split('/')[-1].replace('-', ' ').title()
                    found_pages.append({
                        "Name": title,
                        "Schema": classify_schema(page_url, domain),
                        "URL": page_url,
                        "Source": "Sitemap Recursive"
                    })
                    
    except Exception:
        pass
    
    return found_pages

# --- STRATEGIES ---

def strategy_shopify(domain):
    try:
        url = f"{domain}/products.json?limit=250"
        r = requests.get(url, headers=HEADERS, timeout=3)
        if r.status_code == 200:
            data = r.json()
            if 'products' in data and len(data['products']) > 0:
                return [{
                    "Name": p.get('title'),
                    "Schema": "Retail Product",
                    "URL": f"{domain}/products/{p.get('handle')}",
                    "Source": "Shopify API"
                } for p in data['products']]
    except: pass
    return []

def strategy_universal_scan(domain):
    found_items = {}
    
    # 1. RECURSIVE Sitemap Scan
    # We try standard paths. The recursive function handles the rest.
    sitemaps = [f"{domain}/sitemap.xml", f"{domain}/sitemap_index.xml", f"{domain}/wp-sitemap.xml"]
    
    for sm_url in sitemaps:
        items = fetch_sitemap_urls(sm_url, domain)
        if items:
            for i in items:
                found_items[i['URL']] = i
            break # Stop if we found a valid sitemap tree

    # 2. Homepage Nav (Fallback if sitemap fails or is empty)
    if len(found_items) < 5:
        try:
            r = requests.get(domain, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a.get('href')
                full_url = urljoin(domain, href)
                full_url = clean_link(full_url)
                
                if domain not in full_url: continue
                
                if is_valid_candidate(full_url, domain):
                    if full_url not in found_items:
                        title = a.get_text(strip=True) or full_url.split('/')[-1].replace('-', ' ').title()
                        found_items[full_url] = {
                            "Name": title,
                            "Schema": classify_schema(full_url, domain),
                            "URL": full_url,
                            "Source": "Homepage Nav"
                        }
        except: pass
    
    return list(found_items.values())[:100]

# --- UI LOGIC ---

st.title("🧩 B2B Schema Discoverer")
st.markdown("Identifies **Solutions**, **Platforms**, and **Flat** (StackAdapt-style) schemas.")

col1, col2 = st.columns([3, 1])
with col1:
    domain_input = st.text_input("Company Domain", placeholder="e.g. 6sense.com")
with col2:
    st.write("") 
    st.write("") 
    run_btn = st.button("🔍 Identify Schema", type="primary", use_container_width=True)

if run_btn and domain_input:
    domain = domain_input.strip()
    if not domain.startswith('http'): domain = 'https://' + domain
    domain = domain.rstrip('/')
    
    st.divider()
    
    with st.status(f"Deep Scanning {domain}...", expanded=True) as status:
        results = []
        
        # 1. Retail API
        api_results = strategy_shopify(domain)
        if api_results: results.extend(api_results)
        
        # 2. Recursive Universal Scan
        if not results:
            scan_results = strategy_universal_scan(domain)
            results.extend(scan_results)
            
        if results:
            status.update(label="Analysis Complete", state="complete", expanded=False)
        else:
            status.update(label="No Data Found", state="error", expanded=False)

    if results:
        df = pd.DataFrame(results)
        
        # Schema Diagnosis
        schema_counts = df['Schema'].value_counts()
        top_schema = schema_counts.idxmax()
        
        st.subheader(f"Detected Strategy: {top_schema}")
        
        if "Solution" in top_schema:
            st.success("✅ **Outcome-Focused:** Sells 'Solutions' (Jobs-to-be-Done).")
        elif "Platform" in top_schema:
            st.info("✅ **Platform-Focused:** Sells a unified engine with nested capabilities.")
        elif "Flat" in top_schema:
            st.warning("✅ **Traffic-Focused (Flat):** Products at root level for SEO.")
        
        st.dataframe(
            df,
            column_config={
                "URL": st.column_config.LinkColumn("Link"),
                "Schema": st.column_config.TextColumn("Schema Type"),
            },
            use_container_width=True,
            hide_index=True
        )
        
        clean_name = domain_input.replace('.', '_')
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Download Catalog CSV", csv, f"{clean_name}_schema.csv", "text/csv")
    else:
        st.error("No structure found.")
        st.markdown(f"**Debug:** Could not access sitemap at `{domain}/sitemap.xml`. The site may strictly block bots.")
