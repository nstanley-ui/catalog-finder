import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
import time
from urllib.parse import urljoin, urlparse

# --- CONFIGURATION ---
st.set_page_config(page_title="Universal Catalog Discoverer", page_icon="🕵️", layout="wide")

# Mimic a real browser to avoid 403 Forbidden errors from strict firewalls
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.google.com/'
}

def clean_url(url):
    """Ensures URL has schema and no trailing slash"""
    url = url.strip()
    if not url.startswith('http'):
        url = 'https://' + url
    return url.rstrip('/')

# --- DISCOVERY STRATEGIES ---

def strategy_shopify(domain):
    """
    Strategy 1: The Shopify 'Backdoor'
    Perfect for: Gymshark, Allbirds, Kylie Cosmetics.
    """
    try:
        url = f"{domain}/products.json?limit=250"
        r = requests.get(url, headers=HEADERS, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if 'products' in data and len(data['products']) > 0:
                products = []
                for p in data['products']:
                    # Get first variant price
                    price = "N/A"
                    if p.get('variants'):
                        price = p['variants'][0].get('price')
                    
                    products.append({
                        "Name": p.get('title'),
                        "Price": price,
                        "Type": p.get('product_type', 'Product'),
                        "URL": f"{domain}/products/{p.get('handle')}",
                        "Method": "Shopify API (Exact)"
                    })
                return products
    except Exception:
        pass
    return []

def strategy_sitemap_universal(domain):
    """
    Strategy 2: Universal Sitemap Scanning (B2B & B2C)
    Perfect for: 6sense, Salesforce, Mid-market B2B.
    Checks for 'product', 'solution', 'platform', 'service'.
    """
    try:
        # Common sitemap locations
        sitemap_urls = [
            f"{domain}/sitemap.xml",
            f"{domain}/sitemap_index.xml",
            f"{domain}/sitemap-pages.xml"
        ]
        
        found_urls = []
        
        for sm_url in sitemap_urls:
            try:
                r = requests.get(sm_url, headers=HEADERS, timeout=6)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.content, 'xml')
                    locs = soup.find_all('loc')
                    
                    # Broader keywords for B2B/SaaS
                    keywords = [
                        '/product', '/item', '/p/',  # Retail
                        '/solution', '/platform', '/service', '/feature', '/software' # B2B / SaaS
                    ]
                    
                    for u in locs:
                        url_text = u.text
                        if any(k in url_text for k in keywords):
                            found_urls.append(url_text)
                    
                    # If we found links, stop checking other sitemaps
                    if found_urls:
                        break
            except:
                continue

        # Process found URLs
        results = []
        for url in found_urls[:40]: # Limit to 40 to stay lightweight
            # Guess the type based on keyword
            p_type = "Product"
            if "solution" in url: p_type = "Solution"
            elif "platform" in url: p_type = "Platform"
            elif "service" in url: p_type = "Service"

            results.append({
                "Name": url.split('/')[-1].replace('-', ' ').title(),
                "Price": "Request Info", # B2B rarely has prices
                "Type": p_type,
                "URL": url,
                "Method": "Sitemap Scan (Universal)"
            })
            
        return results
    except Exception:
        pass
    return []

def strategy_metadata_scrape(domain):
    """
    Strategy 3: Metadata & Schema Extraction
    Perfect for: SEO-heavy sites that hide sitemaps.
    """
    try:
        r = requests.get(domain, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(r.text, 'html.parser')
        results = []

        # 3a. Check JSON-LD (Structured Data)
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                if not isinstance(data, list): data = [data]
                for item in data:
                    if item.get('@type') in ['Product', 'SoftwareApplication', 'Service']:
                        results.append({
                            "Name": item.get('name'),
                            "Price": item.get('offers', {}).get('price', 'N/A'),
                            "Type": item.get('@type'),
                            "URL": item.get('url', domain),
                            "Method": "Schema.org (Hidden Data)"
                        })
            except: continue
            
        if results: return results

        # 3b. Fallback: Just get the Page Meta Description if nothing else works
        # This ensures the user sees SOMETHING about the company.
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            return [{
                "Name": soup.title.string if soup.title else "Home Page",
                "Price": "N/A",
                "Type": "Company Summary",
                "URL": domain,
                "Method": "Meta Description Fallback"
            }]
            
    except Exception:
        pass
    return []

# --- UI LAYOUT ---

st.title("🕵️ Universal Catalog Discoverer")
st.markdown("""
**Find products & services for any company (B2C Retail or B2B SaaS).**
Strategies used:
1.  **Shopify API:** Finds hidden JSON feeds (Retail).
2.  **Universal Sitemap:** Scans for 'products', 'solutions', 'platforms' (B2B).
3.  **Schema Scraping:** Extracts SEO structured data.
""")

col1, col2 = st.columns([3, 1])
with col1:
    domain_input = st.text_input("Company Domain", placeholder="e.g. 6sense.com or gymshark.com")
with col2:
    st.write("") # Spacer
    st.write("") 
    run_btn = st.button("🚀 Scan Domain", type="primary", use_container_width=True)

if run_btn and domain_input:
    domain = clean_url(domain_input)
    st.divider()
    
    products = []
    
    with st.status(f"🔍 Analyzing {domain}...", expanded=True) as status:
        
        # 1. Retail Check (Shopify)
        st.write("Checking for Retail/Shopify structure...")
        products = strategy_shopify(domain)
        
        # 2. B2B/Universal Sitemap Check
        if not products:
            st.write("Checking Sitemap for Products, Solutions, & Platforms...")
            products = strategy_sitemap_universal(domain)
            
        # 3. Metadata Check
        if not products:
            st.write("Deep scanning Homepage metadata...")
            products = strategy_metadata_scrape(domain)
            
        if products:
            status.update(label="✅ Success! Data found.", state="complete", expanded=False)
        else:
            status.update(label="❌ No structured data found.", state="error", expanded=False)

    # --- DISPLAY RESULTS ---
    if products:
        # Metrics
        total_items = len(products)
        method_used = products[0]['Method']
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Items Found", total_items)
        m2.metric("Discovery Method", "Sitemap" if "Sitemap" in method_used else "API/Schema")
        m3.metric("Confidence", "High" if "API" in method_used else "Medium")
        
        # Data Table
        df = pd.DataFrame(products)
        
        # Reorder columns if they exist
        cols = ['Name', 'Type', 'Price', 'URL', 'Method']
        df = df[[c for c in cols if c in df.columns]]
        
        st.dataframe(
            df,
            column_config={
                "URL": st.column_config.LinkColumn("Link"),
                "Price": st.column_config.TextColumn("Price/Action"),
            },
            use_container_width=True,
            hide_index=True
        )
        
        # Download
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="⬇️ Download Catalog CSV",
            data=csv,
            file_name=f"{domain_input}_catalog.csv",
            mime="text/csv"
        )
        
    else:
        st.warning("⚠️ No catalog data found.")
        st.info("""
        **Why?**
        - The site might be a heavy Single Page App (React/Vue) that builds HTML only in the browser.
        - They might block bots strictly (Cloudflare).
        - **Next Step:** Try a retail brand (e.g., 'allbirds.com') to see the retail logic work, or a simpler B2B site.
        """)
