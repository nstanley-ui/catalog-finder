import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
import re
from urllib.parse import urljoin, urlparse

# --- CONFIGURATION ---
st.set_page_config(page_title="Universal Catalog Discoverer", page_icon="🕵️", layout="wide")

# Mimic a real browser to avoid 403 Forbidden errors
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
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
    Strategy 1: Shopify API (Retail)
    Checks for hidden /products.json feed.
    """
    try:
        url = f"{domain}/products.json?limit=250"
        r = requests.get(url, headers=HEADERS, timeout=4)
        if r.status_code == 200:
            data = r.json()
            if 'products' in data and len(data['products']) > 0:
                products = []
                for p in data['products']:
                    price = p['variants'][0].get('price') if p.get('variants') else "N/A"
                    products.append({
                        "Name": p.get('title'),
                        "Type": "Product (Retail)",
                        "URL": f"{domain}/products/{p.get('handle')}",
                        "Method": "Shopify API"
                    })
                return products
    except Exception:
        pass
    return []

def strategy_nav_scan(domain):
    """
    Strategy 2: Homepage Navigation Scan (B2B & Retail)
    Fetches the homepage and looks for links with keywords like 'platform', 'solution'.
    This catches 6sense.com/platform/... even if sitemap is missing.
    """
    try:
        r = requests.get(domain, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Keywords to look for in URLs
        keywords = [
            '/product', '/item', '/p/',           # Retail
            '/platform/', '/solution/', '/feature', # B2B / SaaS (Matches 6sense)
            '/software', '/service'
        ]
        
        found_items = {}
        
        # Scan all links on homepage
        for a in soup.find_all('href'==True) + soup.find_all('a'):
            href = a.get('href')
            if not href: continue
            
            full_url = urljoin(domain, href)
            
            # Check if internal link and matches keyword
            if domain in full_url and any(k in full_url for k in keywords):
                # Clean up title
                title = a.get_text(strip=True)
                if not title:
                    # Fallback: extract from URL
                    title = full_url.strip('/').split('/')[-1].replace('-', ' ').title()
                
                # Deduplicate by URL
                if full_url not in found_items:
                    # Determine Type
                    p_type = "Product"
                    if "platform" in full_url: p_type = "Platform"
                    elif "solution" in full_url: p_type = "Solution"
                    
                    found_items[full_url] = {
                        "Name": title,
                        "Type": p_type,
                        "URL": full_url,
                        "Method": "Homepage Nav Scan"
                    }
        
        return list(found_items.values())[:30] # Return top 30 unique links
    except Exception:
        pass
    return []

def strategy_sitemap(domain):
    """
    Strategy 3: Universal Sitemap
    Checks sitemap.xml for the same B2B/Retail keywords.
    """
    try:
        # Common sitemap locations
        sitemap_urls = [
            f"{domain}/sitemap.xml",
            f"{domain}/sitemap_index.xml",
            f"{domain}/wp-sitemap.xml"
        ]
        
        for sm_url in sitemap_urls:
            try:
                r = requests.get(sm_url, headers=HEADERS, timeout=5)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.content, 'xml')
                    urls = [u.text for u in soup.find_all('loc')]
                    
                    keywords = ['/product', '/solution', '/platform', '/service']
                    found = []
                    
                    for u in urls:
                        if any(k in u for k in keywords):
                            p_type = "Product"
                            if "platform" in u: p_type = "Platform"
                            elif "solution" in u: p_type = "Solution"
                            
                            found.append({
                                "Name": u.split('/')[-1].replace('-', ' ').title(),
                                "Type": p_type,
                                "URL": u,
                                "Method": "Sitemap Scan"
                            })
                    
                    if found:
                        return found[:40]
            except:
                continue
    except Exception:
        pass
    return []

# --- UI LAYOUT ---

st.title("🕵️ Universal Catalog Discoverer")
st.markdown("Finds products, platforms, and solutions for **Retail** (Shopify) and **B2B** (SaaS).")

col1, col2 = st.columns([3, 1])
with col1:
    domain_input = st.text_input("Company Domain", placeholder="e.g. 6sense.com")
with col2:
    st.write("")
    st.write("")
    run_btn = st.button("🚀 Find Catalog", type="primary", use_container_width=True)

if run_btn and domain_input:
    domain = clean_url(domain_input)
    st.divider()
    
    with st.status(f"Scanning {domain}...", expanded=True) as status:
        
        # 1. Shopify Check
        st.write("Checking API endpoints...")
        results = strategy_shopify(domain)
        
        # 2. Homepage Nav Check (The fix for 6sense)
        if not results:
            st.write("Scanning homepage navigation...")
            results = strategy_nav_scan(domain)
            
        # 3. Sitemap Check
        if not results:
            st.write("Parsing sitemaps...")
            results = strategy_sitemap(domain)
            
        if results:
            status.update(label="✅ Catalog Found!", state="complete", expanded=False)
        else:
            status.update(label="❌ No data found.", state="error", expanded=False)

    if results:
        # Metrics
        st.success(f"Found {len(results)} items via **{results[0]['Method']}**")
        
        # Display Data
        df = pd.DataFrame(results)
        st.dataframe(
            df,
            column_config={
                "URL": st.column_config.LinkColumn("Link"),
                "Type": st.column_config.TextColumn("Category"),
            },
            use_container_width=True,
            hide_index=True
        )
        
        # CSV Download
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"{domain_input}_catalog.csv",
            mime="text/csv"
        )
    else:
        st.warning("Could not automatically extract catalog.")
        st.markdown(f"""
        **Troubleshooting:**
        - The site `{domain}` might be fully dynamic (JavaScript).
        - Try a different domain to confirm the tool works.
        """)
