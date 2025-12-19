import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urljoin

# --- CONFIGURATION ---
st.set_page_config(page_title="B2B Schema Discoverer", page_icon="🧩", layout="wide")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

# --- 1. TARGET SCHEMAS (Based on your Analysis) ---
TARGET_PATTERNS = {
    '/products/': 'Product Suite',
    '/product/': 'Product Suite',
    '/software/': 'Product Suite (Software)',
    '/platform/': 'Unified Platform',
    '/features/': 'Feature / Module',
    '/solutions/': 'Solution (Job-to-be-Done)',
    '/solution/': 'Solution (Job-to-be-Done)',
    '/modules/': 'Platform Module'
}

# --- 2. NOISE FILTERING ---
BLACKLIST_KEYWORDS = [
    'career', 'job', 'hiring', 'apply',       # HR
    'policy', 'privacy', 'terms', 'legal',    # Legal
    'blog', 'news', 'press', 'release',       # Content
    'login', 'signin', 'register', 'account', # Auth
    'about', 'contact', 'investor', 'faq',    # Info
    'support', 'help', 'docs', 'developers',  # Support
    'customer-stories', 'case-studies'        # Marketing Content
]

def is_valid_url(url):
    """Checks if URL matches a Target Pattern and is not Blacklisted"""
    url_lower = url.lower()
    
    # Must match at least one Target Pattern
    if not any(pattern in url_lower for pattern in TARGET_PATTERNS.keys()):
        return False
        
    # Must NOT match any Blacklist word
    for bad_word in BLACKLIST_KEYWORDS:
        if bad_word in url_lower:
            return False
            
    return True

def clean_link(url):
    """Removes query params (?utm=...) and trailing slashes for deduplication"""
    if not url: return ""
    return url.split('?')[0].split('#')[0].rstrip('/')

def classify_schema(url):
    """Maps a URL to its Schema Type (Suite, Platform, or Solution)"""
    url_lower = url.lower()
    for pattern, schema_name in TARGET_PATTERNS.items():
        if pattern in url_lower:
            return schema_name
    return "Other"

# --- STRATEGIES ---

def strategy_shopify(domain):
    """Check for hidden Shopify JSON feed (Retail/Midmarket)"""
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

def strategy_nav_scan(domain):
    """Scans Homepage Navigation for Schema Patterns"""
    try:
        r = requests.get(domain, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(r.text, 'html.parser')
        found_items = {}
        
        # Scan all links
        for a in soup.find_all('a', href=True):
            href = a.get('href')
            full_url = urljoin(domain, href)
            full_url = clean_link(full_url) # Clean it immediately
            
            if domain not in full_url: continue
            if not is_valid_url(full_url): continue
            
            # Extract Title
            title = a.get_text(strip=True)
            if not title or len(title) > 60: 
                # Fallback: Extract from URL slug
                title = full_url.split('/')[-1].replace('-', ' ').title()
                
            if full_url not in found_items:
                found_items[full_url] = {
                    "Name": title,
                    "Schema": classify_schema(full_url),
                    "URL": full_url,
                    "Source": "Homepage Scan"
                }
        return list(found_items.values())[:40]
    except: pass
    return []

def strategy_sitemap(domain):
    """Scans Sitemaps for Schema Patterns"""
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
                        u = clean_link(u)
                        if is_valid_url(u):
                            found.append({
                                "Name": u.split('/')[-1].replace('-', ' ').title(),
                                "Schema": classify_schema(u),
                                "URL": u,
                                "Source": "Sitemap Scan"
                            })
                    if found: return found[:50]
            except: continue
    except: pass
    return []

# --- UI LOGIC ---

st.title("🧩 B2B Schema Discoverer")
st.markdown("""
Identify a company's architecture: **Product Suite**, **Unified Platform**, or **Solution-First**.
""")

col1, col2 = st.columns([3, 1])
with col1:
    domain_input = st.text_input("Company Domain", placeholder="e.g. atlassian.com, gong.io, hubspot.com")
with col2:
    st.write("") 
    st.write("") 
    run_btn = st.button("🔍 Analyze Domain", type="primary", use_container_width=True)

if run_btn and domain_input:
    domain = domain_input.strip()
    if not domain.startswith('http'): domain = 'https://' + domain
    domain = domain.rstrip('/')
    
    st.divider()
    
    with st.status(f"Scanning {domain} for schemas...", expanded=True) as status:
        results = []
        
        # 1. Quick API Check
        api_results = strategy_shopify(domain)
        if api_results:
            results.extend(api_results)
            st.write("✅ Found Retail/Shopify structure.")
        
        # 2. Homepage Scan (High fidelity for navigation structure)
        if not results:
            st.write("scanning homepage navigation...")
            nav_results = strategy_nav_scan(domain)
            results.extend(nav_results)
            
        # 3. Sitemap Scan (Deep dive)
        if len(results) < 5:
            st.write("Deep scanning sitemaps...")
            map_results = strategy_sitemap(domain)
            # Merge without duplicates
            existing_urls = {r['URL'] for r in results}
            for item in map_results:
                if item['URL'] not in existing_urls:
                    results.append(item)
                    
        if results:
            status.update(label="Analysis Complete", state="complete", expanded=False)
        else:
            status.update(label="No structured catalog found", state="error", expanded=False)

    if results:
        df = pd.DataFrame(results)
        
        # --- SCHEMA DETECTION LOGIC ---
        # Count the types of schemas found to guess the company strategy
        schema_counts = df['Schema'].value_counts()
        dominant_schema = schema_counts.idxmax()
        
        st.subheader(f"Strategy Detected: {dominant_schema}")
        
        if "Platform" in dominant_schema:
            st.info(f"💡 **Unified Platform:** This company positions its offering as a single system with multiple capabilities ({len(df)} modules found).")
        elif "Solution" in dominant_schema:
            st.info(f"💡 **Solution-Led:** This company sells based on 'Jobs to be Done' rather than tool names.")
        elif "Suite" in dominant_schema or "Software" in dominant_schema:
            st.info(f"💡 **Product Suite:** This company acts as a directory of distinct, standalone tools.")
        
        # Display Data
        st.dataframe(
            df,
            column_config={
                "URL": st.column_config.LinkColumn("Link"),
                "Schema": st.column_config.TextColumn("Schema Type", help="How the URL is structured"),
            },
            use_container_width=True,
            hide_index=True
        )
        
        # Download
        clean_name = domain_input.replace('.', '_')
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Download Catalog CSV", csv, f"{clean_name}_catalog.csv", "text/csv")

    else:
        st.warning("No catalog data found matching standard schemas.")
        st.markdown("**Try checking:** Is the site a Single Page App (React)? Or does it use a non-standard URL structure?")
