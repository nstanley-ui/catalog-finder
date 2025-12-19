import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
import time
from urllib.parse import urljoin, urlparse

# --- CONFIGURATION ---
st.set_page_config(page_title="Catalog Discovery Tool", page_icon="🛍️")

# Mimic a real browser to avoid 403 Forbidden errors
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}

def clean_url(url):
    """Ensures URL has schema and no trailing slash for consistency"""
    url = url.strip()
    if not url.startswith('http'):
        url = 'https://' + url
    return url.rstrip('/')

# --- DISCOVERY MODULES ---

def strategy_shopify(domain):
    """
    Strategy 1: The Shopify 'Backdoor'
    Many midmarket brands (Gymshark, Allbirds, etc.) expose a JSON feed.
    """
    try:
        url = f"{domain}/products.json?limit=250"
        r = requests.get(url, headers=HEADERS, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if 'products' in data and len(data['products']) > 0:
                products = []
                for p in data['products']:
                    variant_price = p['variants'][0].get('price') if p.get('variants') else 'N/A'
                    products.append({
                        "Name": p.get('title'),
                        "Price": variant_price,
                        "URL": f"{domain}/products/{p.get('handle')}",
                        "Method": "Shopify API (High Confidence)"
                    })
                return products
    except Exception:
        pass
    return []

def strategy_sitemap(domain):
    """
    Strategy 2: Sitemap Scanning
    Parses sitemap.xml for URLs containing 'product' or 'item'.
    """
    try:
        sitemap_url = f"{domain}/sitemap.xml"
        r = requests.get(sitemap_url, headers=HEADERS, timeout=5)
        if r.status_code == 200:
            soup = BeautifulSoup(r.content, 'xml') # XML parsing
            locs = soup.find_all('loc')
            
            # Filter for product-looking URLs
            product_urls = [
                u.text for u in locs 
                if '/product' in u.text or '/item' in u.text or '/p/' in u.text
            ]
            
            # Return top 20 to keep it lightweight
            return [{
                "Name": "Detected via Sitemap",
                "Price": "N/A (Click URL)",
                "URL": url,
                "Method": "Sitemap Scan"
            } for url in product_urls[:20]]
    except Exception:
        pass
    return []

def strategy_metadata(domain):
    """
    Strategy 3: HTML Meta Data & Schema.org
    Scrapes the homepage for structured JSON-LD data.
    """
    try:
        r = requests.get(domain, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(r.text, 'html.parser')
        found_products = []

        # Look for JSON-LD scripts
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                # Normalize to list
                if not isinstance(data, list):
                    data = [data]
                
                for item in data:
                    if item.get('@type') == 'Product':
                        found_products.append({
                            "Name": item.get('name', 'Unknown'),
                            "Price": item.get('offers', {}).get('price', 'N/A'),
                            "URL": item.get('url', domain),
                            "Method": "Schema.org (Metadata)"
                        })
            except:
                continue
        return found_products
    except Exception:
        pass
    return []

# --- UI LAYOUT ---

st.title("🛍️ Midmarket Catalog Finder")
st.markdown("""
This lightweight tool attempts to extract product data using three strategies:
1. **Shopify API Check** (Hidden JSON feeds)
2. **Schema.org Extraction** (Hidden SEO metadata)
3. **Sitemap Heuristics** (URL pattern matching)
""")

target_domain = st.text_input("Enter Company Domain", placeholder="e.g. allbirds.com")
run_btn = st.button("Find Catalog", type="primary")

if run_btn and target_domain:
    domain = clean_url(target_domain)
    
    with st.status(f"Scanning {domain}...", expanded=True) as status:
        
        # 1. Try Shopify
        st.write("Checking Shopify endpoints...")
        products = strategy_shopify(domain)
        
        # 2. Try Metadata if no Shopify
        if not products:
            st.write("Checking Schema.org metadata...")
            products = strategy_metadata(domain)
            
        # 3. Try Sitemap if still nothing
        if not products:
            st.write("Scanning sitemap structure...")
            products = strategy_sitemap(domain)
            
        status.update(label="Scan Complete", state="complete", expanded=False)

    st.divider()

    if products:
        st.success(f"Found {len(products)} items via **{products[0]['Method']}**")
        df = pd.DataFrame(products)
        st.dataframe(
            df, 
            column_config={
                "URL": st.column_config.LinkColumn("Product Link")
            },
            use_container_width=True
        )
        
        # Download Button
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Catalog as CSV",
            data=csv,
            file_name=f"{target_domain}_catalog.csv",
            mime="text/csv"
        )
    else:
        st.warning("⚠️ No catalog found using lightweight methods.")
        st.info("Tip: The site might be using a strict firewall or a Single Page App (React/Vue) that hides data from simple scanners.")
