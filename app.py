import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urljoin, urlparse

# --- CONFIGURATION ---
st.set_page_config(page_title="B2B Schema Discoverer", page_icon="🧩", layout="wide")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

# --- 1. SCHEMA DEFINITIONS ---
# Standard Directories (Demandbase / 6sense)
DIRECTORY_PATTERNS = {
    '/products/': 'Product Suite',
    '/product/': 'Product Suite',
    '/platform/': 'Platform Feature',       # 6sense Style
    '/solutions/': 'Solution (Use Case)',   # Demandbase Style
    '/features/': 'Platform Feature',
    '/software/': 'Product Suite',
    '/capabilities/': 'Platform Feature'
}

# --- 2. FLAT SCHEMA KEYWORDS (StackAdapt Style) ---
# If a URL is at the root (domain.com/xyz), it MUST contain one of these to be accepted.
# This prevents grabbing /about, /legal, /contact.
FLAT_SCHEMA_KEYWORDS = [
    'advertising', 'marketing', 'intelligence', 'sales', 'revenue',
    'programmatic', 'dsp', 'campaign', 'channel', 'inventory',
    'native', 'display', 'video', 'audio', 'connected-tv', 'ctv',
    'abm', 'b2b', 'data', 'cloud', 'engine', 'studio'
]

# --- 3. NOISE FILTERING ---
BLACKLIST_KEYWORDS = [
    'career', 'job', 'hiring', 'apply', 'team', 'people',       # HR
    'policy', 'privacy', 'terms', 'legal', 'gdpr', 'security',  # Legal
    'blog', 'news', 'press', 'release', 'media', 'events',      # Content
    'login', 'signin', 'register', 'account', 'portal',         # Auth
    'about', 'contact', 'investor', 'faq', 'support', 'help',   # Info
    'customer', 'case-study', 'resource', 'ebook', 'webinar'    # Marketing Content
]

def clean_link(url):
    """Removes query params and trailing slashes"""
    if not url: return ""
    return url.split('?')[0].split('#')[0].rstrip('/')

def is_root_url(domain, url):
    """Checks if a URL is strictly at the root level (domain.com/slug)"""
    # Remove protocol and domain to get path
    path = url.replace(domain, '').strip('/')
    return '/' not in path and path != ''

def classify_schema(url, domain):
    """Maps URL to Schema Type: Directory vs. Flat"""
    
    # 1. Check Directory Patterns (Priority)
    for pattern, schema_name in DIRECTORY_PATTERNS.items():
        if pattern in url.lower():
            return schema_name
            
    # 2. Check Flat Schema (Root Level)
    if is_root_url(domain, url):
        return "Flat / Root (High Volume)"
        
    return "Other Product Page"

def is_valid_candidate(url, domain):
    """Decides if a URL is worth keeping"""
    url_lower = url.lower()
    
    # 1. HARD EXCLUSION (Blacklist)
    if any(bad in url_lower for bad in BLACKLIST_KEYWORDS):
        return False
        
    # 2. DIRECTORY CHECK (Easy Yes)
    if any(pattern in url_lower for pattern in DIRECTORY_PATTERNS.keys()):
        return True
        
    # 3. FLAT SCHEMA CHECK (Hard Yes - Requires Keywords)
    # If it is a root URL, it MUST have a business keyword
    if is_root_url(domain, url):
        if any(kw in url_lower for kw in FLAT_SCHEMA_KEYWORDS):
            return True
            
    return False

# --- STRATEGIES ---

def strategy_shopify(domain):
    """Retail Check (Hidden JSON)"""
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
    """
    Combines Nav Scan and Sitemap Scan into one powerful pass.
    Handles 'Flat Schema' by checking root URLs against B2B keywords.
    """
    found_items = {}
    
    # 1. Scan Sitemap (Best for Demandbase/6sense)
    try:
        sitemaps = [f"{domain}/sitemap.xml", f"{domain}/sitemap_index.xml", f"{domain}/wp-sitemap.xml"]
        for sm_url in sitemaps:
            try:
                r = requests.get(sm_url, headers=HEADERS, timeout=5)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.content, 'xml')
                    urls = [u.text for u in soup.find_all('loc')]
                    for u in urls:
                        u = clean_link(u)
                        if is_valid_candidate(u, domain):
                            title = u.split('/')[-1].replace('-', ' ').title()
                            found_items[u] = {
                                "Name": title,
                                "Schema": classify_schema(u, domain),
                                "URL": u,
                                "Source": "Sitemap"
                            }
                    if found_items: break # Stop if we found a working sitemap
            except: continue
    except: pass

    # 2. Scan Homepage Nav (Best for StackAdapt/Flat links hidden from sitemap)
    try:
        r = requests.get(domain, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(r.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a.get('href')
            full_url = urljoin(domain, href)
            full_url = clean_link(full_url)
            
            if domain not in full_url: continue
            
            if is_valid_candidate(full_url, domain):
                # Only add if not already found in sitemap
                if full_url not in found_items:
                    title = a.get_text(strip=True)
                    if not title or len(title) > 50:
                        title = full_url.split('/')[-1].replace('-', ' ').title()
                    
                    found_items[full_url] = {
                        "Name": title,
                        "Schema": classify_schema(full_url, domain),
                        "URL": full_url,
                        "Source": "Homepage Nav"
                    }
    except: pass
    
    return list(found_items.values())[:60]

# --- UI LOGIC ---

st.title("🧩 B2B Schema Discoverer")
st.markdown("""
Analyzes structure:
1. **Solution-Based** (`/solutions/` - e.g. Demandbase)
2. **Platform-Based** (`/platform/` - e.g. 6sense)
3. **Flat / Root** (`/native-advertising` - e.g. StackAdapt)
""")

col1, col2 = st.columns([3, 1])
with col1:
    domain_input = st.text_input("Company Domain", placeholder="e.g. stackadapt.com")
with col2:
    st.write("") 
    st.write("") 
    run_btn = st.button("🔍 Identify Schema", type="primary", use_container_width=True)

if run_btn and domain_input:
    domain = domain_input.strip()
    if not domain.startswith('http'): domain = 'https://' + domain
    domain = domain.rstrip('/')
    
    st.divider()
    
    with st.status(f"Scanning {domain}...", expanded=True) as status:
        results = []
        
        # 1. Retail API
        api_results = strategy_shopify(domain)
        if api_results: results.extend(api_results)
        
        # 2. Universal Scan (Sitemap + Flat Heuristics)
        if not results:
            scan_results = strategy_universal_scan(domain)
            results.extend(scan_results)
            
        if results:
            status.update(label="Analysis Complete", state="complete", expanded=False)
        else:
            status.update(label="No Data Found", state="error", expanded=False)

    if results:
        df = pd.DataFrame(results)
        
        # --- INTELLIGENT SCHEMA DIAGNOSIS ---
        schema_counts = df['Schema'].value_counts()
        top_schema = schema_counts.idxmax()
        
        st.subheader(f"Detected Strategy: {top_schema}")
        
        if "Solution" in top_schema:
            st.success("✅ **Outcome-Focused:** This site sells 'Solutions' (Jobs-to-be-Done) rather than just tools.")
        elif "Platform" in top_schema:
            st.info("✅ **Platform-Focused:** This site sells a unified engine with features nested as modules.")
        elif "Flat" in top_schema:
            st.warning("✅ **Traffic-Focused (Flat):** This site places products at the root level to capture high-intent SEO traffic (e.g., 'Native Advertising').")
        
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
        st.markdown("If this is a **StackAdapt-style** site, ensure the links contain keywords like 'advertising' or 'channel'.")
