"""
Full SHL Product Catalog Scraper
Scrapes all Individual Test Solutions with detailed info from product pages.
"""
import requests
from bs4 import BeautifulSoup
import json
import time
import re
import concurrent.futures

BASE_URL = "https://www.shl.com/solutions/products/product-catalog/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TEST_TYPE_MAP = {
    "A": "Ability & Aptitude",
    "B": "Biodata & Situational Judgement",
    "C": "Competencies",
    "D": "Development & 360",
    "E": "Assessment Exercises",
    "K": "Knowledge & Skills",
    "P": "Personality & Behavior",
    "S": "Simulations",
}

def scrape_catalog_page(start=0, type_id=1):
    """Scrape a single page of the catalog, extracting table data properly."""
    params = {"start": start, "type": type_id}
    try:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error fetching page start={start}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    products = []
    
    table = soup.find("table")
    if not table:
        return products
    
    rows = table.find_all("tr")
    for row in rows[1:]: 
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        
        link = cells[0].find("a")
        if not link:
            continue
        name = link.get_text(strip=True)
        href = link.get("href", "")
        if not href.startswith("http"):
            href = "https://www.shl.com" + href
    
        remote_span = cells[1].find("span", class_=re.compile(r"-yes"))
        remote_testing = remote_span is not None

        adaptive_span = cells[2].find("span", class_=re.compile(r"-yes"))
        adaptive_irt = adaptive_span is not None
        test_type = cells[3].get_text(strip=True)
        
        products.append({
            "name": name,
            "url": href,
            "remote_testing": remote_testing,
            "adaptive_irt": adaptive_irt,
            "test_type": test_type,
        })
    
    return products


def scrape_product_detail(product):
    """Scrape detailed info from an individual product page."""
    url = product["url"]
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"  Error scraping {url}: {e}")
        return product

    soup = BeautifulSoup(resp.text, "html.parser")
    main = soup.find("main")
    if not main:
        return product
    
    text = main.get_text(separator="\n", strip=True)
    
    desc_match = re.search(r"Description\n(.+?)(?:\nJob levels|\nLanguages|\nAssessment length|\nTest Type)", text, re.DOTALL)
    if desc_match:
        product["description"] = desc_match.group(1).strip()
    
    job_match = re.search(r"Job levels\n(.+?)(?:\nLanguages|\nAssessment length|\nTest Type)", text, re.DOTALL)
    if job_match:
        product["job_levels"] = [jl.strip().rstrip(",") for jl in job_match.group(1).strip().split(",") if jl.strip().rstrip(",")]

    lang_match = re.search(r"Languages\n(.+?)(?:\nAssessment length|\nTest Type)", text, re.DOTALL)
    if lang_match:
        product["languages"] = [l.strip().rstrip(",") for l in lang_match.group(1).strip().split(",") if l.strip().rstrip(",")]

    length_match = re.search(r"Approximate Completion Time in minutes\s*=\s*(\d+)", text)
    if length_match:
        product["duration_minutes"] = int(length_match.group(1))

    type_section = re.search(r"Test Type:\n(.+?)(?:\nRemote Testing|\nAdaptive|\nDownloads)", text, re.DOTALL)
    if type_section:
        type_codes = re.findall(r"\b([ABCDEKPS])\b", type_section.group(1))
        if type_codes:
            product["test_type_codes"] = list(set(type_codes))
            product["test_type_labels"] = [TEST_TYPE_MAP.get(c, c) for c in product["test_type_codes"]]
    
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and not product.get("description"):
        product["description"] = meta_desc.get("content", "").split(":")[1].strip() if ":" in meta_desc.get("content", "") else meta_desc.get("content", "")
    
    return product


def main():
    print("=" * 60)
    print("SHL Full Product Catalog Scraper")
    print("=" * 60)
    
    print("\n[Step 1] Scraping catalog listings...")
    all_products = []
    
    for start in range(0, 384, 12):
        products = scrape_catalog_page(start=start, type_id=1)
        all_products.extend(products)
        print(f"  Page start={start}: {len(products)} products (total: {len(all_products)})")
        time.sleep(0.3)
    
    seen = set()
    unique = []
    for p in all_products:
        if p["url"] not in seen:
            seen.add(p["url"])
            unique.append(p)
    
    print(f"\nTotal unique products from listings: {len(unique)}")
    
    with open("catalog_listings.json", "w", encoding="utf-8") as f:
        json.dump(unique, f, indent=2)

    print(f"\n[Step 2] Scraping {len(unique)} product detail pages...")
    
    def scrape_with_delay(product):
        time.sleep(0.2)
        return scrape_product_detail(product)
    
    detailed_products = []
    batch_size = 10
    for i in range(0, len(unique), batch_size):
        batch = unique[i:i+batch_size]
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(scrape_with_delay, batch))
            detailed_products.extend(results)
        
        completed = min(i + batch_size, len(unique))
        print(f"  Completed: {completed}/{len(unique)}")

        if completed % 50 == 0 or completed == len(unique):
            with open("catalog_full.json", "w", encoding="utf-8") as f:
                json.dump(detailed_products, f, indent=2)
    
    with open("catalog_full.json", "w", encoding="utf-8") as f:
        json.dump(detailed_products, f, indent=2)
    
    print(f"\n{'=' * 60}")
    print(f"DONE! Scraped {len(detailed_products)} products total.")
    print(f"Saved to catalog_full.json")

    with_desc = sum(1 for p in detailed_products if p.get("description"))
    with_dur = sum(1 for p in detailed_products if p.get("duration_minutes"))
    with_lang = sum(1 for p in detailed_products if p.get("languages"))
    with_levels = sum(1 for p in detailed_products if p.get("job_levels"))
    
    print(f"\nStats:")
    print(f"  With description: {with_desc}/{len(detailed_products)}")
    print(f"  With duration: {with_dur}/{len(detailed_products)}")
    print(f"  With languages: {with_lang}/{len(detailed_products)}")
    print(f"  With job levels: {with_levels}/{len(detailed_products)}")

    type_counts = {}
    for p in detailed_products:
        for c in (p.get("test_type") or ""):
            type_counts[c] = type_counts.get(c, 0) + 1
    print(f"\nTest type distribution:")
    for code, count in sorted(type_counts.items()):
        label = TEST_TYPE_MAP.get(code, "Unknown")
        print(f"  {code} ({label}): {count}")

if __name__ == "__main__":
    main()
