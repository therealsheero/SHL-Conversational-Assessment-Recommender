import requests
from bs4 import BeautifulSoup
import json
import time
import re

BASE_URL = "https://www.shl.com/solutions/products/product-catalog/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

def scrape_catalog_page(start=0, type_id=1):
    params = {"start": start, "type": type_id}
    try:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"Error fetching page start={start}: {e}")
        return None

def parse_catalog_page(html):
    soup = BeautifulSoup(html, "html.parser")
    products = []
    
    tables = soup.find_all("table")
    print(f"  Found {len(tables)} tables")
    
    for i, table in enumerate(tables):
        rows = table.find_all("tr")
        print(f"  Table {i}: {len(rows)} rows")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if cells:
                cell_texts = [c.get_text(strip=True) for c in cells]
                print(f"    Row: {cell_texts[:5]}")
                
                
                links = row.find_all("a")
                for link in links:
                    href = link.get("href", "")
                    if "product-catalog/view" in href:
                        name = link.get_text(strip=True)
                        if not href.startswith("http"):
                            href = "https://www.shl.com" + href
                        
                        
                        product = {
                            "name": name,
                            "url": href,
                            "remote_testing": None,
                            "adaptive_irt": None,
                            "test_type": None,
                        }
                        
                       
                        for cell in cells:
                            text = cell.get_text(strip=True)
                            
                            if text in ["A", "B", "C", "D", "E", "K", "P", "S"]:
                                product["test_type"] = text
                            
                            imgs = cell.find_all("img")
                            spans = cell.find_all("span")
                            for img in imgs:
                                alt = img.get("alt", "")
                                src = img.get("src", "")
                                print(f"      IMG: alt={alt}, src={src}")
                        
                        products.append(product)
    
    all_links = soup.find_all("a", href=re.compile(r"product-catalog/view"))
    print(f"  Found {len(all_links)} product links total")
    
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        print(f"  Structured data: {script.string[:200] if script.string else 'empty'}")
    
    main_content = soup.find("main") or soup.find("div", class_=re.compile(r"content|catalog|product"))
    if main_content:
        print(f"  Main content tag: {main_content.name}, classes: {main_content.get('class', [])}")
    
    product_containers = soup.find_all(class_=re.compile(r"product|catalog|assessment|result", re.I))
    for pc in product_containers[:5]:
        print(f"  Product container: <{pc.name} class='{pc.get('class', [])}'> text={pc.get_text(strip=True)[:100]}")
    
    return products

def scrape_individual_product(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        product_info = {"url": url}
        title = soup.find("h1")
        if title:
            product_info["name"] = title.get_text(strip=True)
    
        desc = soup.find("meta", attrs={"name": "description"})
        if desc:
            product_info["description"] = desc.get("content", "")
    
        details = {}

        dls = soup.find_all("dl")
        for dl in dls:
            dts = dl.find_all("dt")
            dds = dl.find_all("dd")
            for dt, dd in zip(dts, dds):
                details[dt.get_text(strip=True)] = dd.get_text(strip=True)
        
        if details:
            product_info["details"] = details
        
        main = soup.find("main")
        if main:
            product_info["content"] = main.get_text(separator="\n", strip=True)[:2000]
        
        return product_info
    except Exception as e:
        print(f"  Error scraping {url}: {e}")
        return {"url": url, "error": str(e)}

def main():
    print("=" * 60)
    print("SHL Product Catalog Scraper")
    print("=" * 60)
    
    print("\n--- Analyzing page structure ---")
    html = scrape_catalog_page(start=0, type_id=1)
    if not html:
        print("Failed to fetch first page!")
        return

    with open("debug_page1.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved raw HTML ({len(html)} bytes) to debug_page1.html")
    
    products = parse_catalog_page(html)
    print(f"\nFound {len(products)} products on page 1")
    
    if products:
        print("\nFirst few products:")
        for p in products[:3]:
            print(f"  {p}")

    all_products = list(products)
    
    for page_start in range(12, 384, 12):
        print(f"\n--- Fetching page start={page_start} ---")
        html = scrape_catalog_page(start=page_start, type_id=1)
        if html:
            page_products = parse_catalog_page(html)
            all_products.extend(page_products)
            print(f"  Got {len(page_products)} products (total: {len(all_products)})")
        time.sleep(0.5)  # Be polite

    seen_urls = set()
    unique_products = []
    for p in all_products:
        if p["url"] not in seen_urls:
            seen_urls.add(p["url"])
            unique_products.append(p)
    
    print(f"\n\nTotal unique products: {len(unique_products)}")

    with open("catalog_basic.json", "w", encoding="utf-8") as f:
        json.dump(unique_products, f, indent=2)
    print("Saved basic catalog to catalog_basic.json")

    print("\n--- Scraping product details (sample of 5) ---")
    for p in unique_products[:5]:
        print(f"\nScraping: {p['name']}")
        details = scrape_individual_product(p["url"])
        p.update(details)
        print(f"  Got details: {list(details.keys())}")
        time.sleep(0.5)

    with open("catalog_detailed_sample.json", "w", encoding="utf-8") as f:
        json.dump(unique_products[:5], f, indent=2)
    print("\nSaved detailed sample to catalog_detailed_sample.json")

if __name__ == "__main__":
    main()
