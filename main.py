# main.py
import json
import os
import random
import time
from typing import List, Dict, Any

import requests
from playwright.sync_api import sync_playwright, Page, Playwright, Browser

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# IMPORTANT: Replace these URLs with your actual search query URLs
# It should be sorted by the newest listings.
NJUSKALO_URL = "https://www.njuskalo.hr/iznajmljivanje-stanova/tresnjevka-jug?price%5Bmax%5D=600"
INDEX_OGLASI_URL = "https://www.index.hr/oglasi/nekretnine/najam-stanova/grad-zagreb/pretraga?searchQuery=%257B%2522category%2522%253A%2522najam-stanova%2522%252C%2522module%2522%253A%2522nekretnine%2522%252C%2522includeCountyIds%2522%253A%255B%2522056b6c84-e6f1-433f-8bdc-9b8dbb86d6fb%2522%255D%252C%2522priceTo%2522%253A%2522600%2522%252C%2522sortOption%2522%253A4%257D"

SEEN_ADS_FILE = "seen_ads.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36"

# --- Helper Functions ---

def load_seen_ads() -> List[str]:
    """Loads seen ad IDs from a JSON file."""
    if os.path.exists(SEEN_ADS_FILE):
        with open(SEEN_ADS_FILE, "r") as f:
            return json.load(f)
    return []

def save_seen_ads(ad_ids: List[str]):
    """Saves seen ad IDs to a JSON file."""
    with open(SEEN_ADS_FILE, "w") as f:
        json.dump(ad_ids, f, indent=4)
    print(f"Successfully saved {len(ad_ids)} ad IDs to {SEEN_ADS_FILE}")

def send_telegram_notification(ad: Dict[str, Any]):
    """Sends a formatted message to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram token or chat ID not set. Skipping notification.")
        return

    message = (
        f"**New Listing Found!**\n\n"
        f"**Title:** {ad['title']}\n"
        f"**Price:** {ad['price']}\n"
        f"**Link:** [Click Here]({ad['link']})"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print(f"Successfully sent notification for ad: {ad['id']}")
    except requests.RequestException as e:
        print(f"Error sending Telegram notification: {e}")

# --- Scraping Functions ---

def scrape_njuskalo(page: Page) -> List[Dict[str, Any]]:
    """Scrapes Njuškalo for apartment listings."""
    print("Scraping Njuškalo...")
    ads = []
    try:
        page.goto(NJUSKALO_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(".EntityList-item", timeout=30000)

        items = page.query_selector_all(".EntityList-item--Regular, .EntityList-item--VauVau")
        
        for item in items:
            ad_id = item.get_attribute("data-id")
            if not ad_id:
                continue

            title_element = item.query_selector(".entity-title a")
            price_element = item.query_selector(".entity-price")
            
            title = title_element.inner_text().strip() if title_element else "N/A"
            link = title_element.get_attribute("href") if title_element else "N/A"
            full_link = f"https://www.njuskalo.hr{link}" if link.startswith('/') else link
            price = price_element.inner_text().strip() if price_element else "N/A"

            ads.append({
                "id": f"njuskalo-{ad_id}",
                "title": title,
                "price": price,
                "link": full_link
            })
    except Exception as e:
        print(f"Error scraping Njuškalo: {e}")
        page.screenshot(path="error_njuskalo.png")
    
    print(f"Found {len(ads)} ads on Njuškalo.")
    return ads

def scrape_index_oglasi(page: Page) -> List[Dict[str, Any]]:
    """Scrapes Index Oglasi for apartment listings."""
    print("Scraping Index Oglasi...")
    ads = []
    try:
        page.goto(INDEX_OGLASI_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(".OglasiRezultati-ad-card", timeout=30000)

        items = page.query_selector_all(".OglasiRezultati-ad-card")
        
        for item in items:
            link_element = item.query_selector("a")
            if not link_element:
                continue
            
            link = link_element.get_attribute("href")
            # Extract ID from URL: e.g., /oglasi/stan-zagreb-tresnjevka-sjever-60-m2/1234567 -> 1234567
            ad_id = link.split('/')[-1] if link else None
            if not ad_id or not ad_id.isdigit():
                 # sometimes the last part is not an id
                 ad_id = link.split('/')[-2] if link else None
                 if not ad_id or not ad_id.isdigit():
                     continue

            title_element = item.query_selector(".title")
            price_element = item.query_selector(".price")
            
            title = title_element.inner_text().strip() if title_element else "N/A"
            price = price_element.inner_text().strip() if price_element else "N/A"
            
            ads.append({
                "id": f"index-{ad_id}",
                "title": title,
                "price": price,
                "link": link
            })
    except Exception as e:
        print(f"Error scraping Index Oglasi: {e}")
        page.screenshot(path="error_index_oglasi.png")

    print(f"Found {len(ads)} ads on Index Oglasi.")
    return ads


# --- Main Execution ---

def main():
    """Main function to run the scraper."""
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables. Exiting.")
        return

    seen_ads = load_seen_ads()
    all_new_ads = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 720}
        )
        page = context.new_page()

        # Scrape sites
        njuskalo_ads = scrape_njuskalo(page)
        time.sleep(random.uniform(3, 7))
        index_ads = scrape_index_oglasi(page)

        all_ads = njuskalo_ads + index_ads
        
        # Process ads
        for ad in all_ads:
            if ad["id"] not in seen_ads:
                print(f"New ad found: {ad['id']} - {ad['title']}")
                all_new_ads.append(ad)
                seen_ads.append(ad['id'])

        # Send notifications and save state
        if all_new_ads:
            print(f"Found {len(all_new_ads)} new ads in total. Sending notifications...")
            for ad in reversed(all_new_ads): # Send oldest first
                send_telegram_notification(ad)
                time.sleep(random.uniform(1, 3)) # Avoid rate limiting
            
            save_seen_ads(seen_ads)
        else:
            print("No new ads found.")

        browser.close()

if __name__ == "__main__":
    main()
