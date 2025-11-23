# main.py
import json
import os
import random
import time
import logging
import re # Added for Njuškalo ID extraction
from typing import List, Dict, Any

import requests
from playwright.sync_api import sync_playwright, Page

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

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
    """Loads seen ad IDs from a JSON file. If the file doesn't exist, creates it."""
    if not os.path.exists(SEEN_ADS_FILE):
        logger.info(f"'{SEEN_ADS_FILE}' not found. Creating a new empty file.")
        with open(SEEN_ADS_FILE, "w") as f:
            json.dump([], f)
        return []
    
    with open(SEEN_ADS_FILE, "r") as f:
        # Handle case where file might be empty or corrupt
        try:
            logger.info(f"Loading seen ads from '{SEEN_ADS_FILE}'.")
            return json.load(f)
        except json.JSONDecodeError:
            logger.warning(f"'{SEEN_ADS_FILE}' is empty or corrupt. Starting with an empty list.")
            return []

def save_seen_ads(ad_ids: List[str]):
    """Saves seen ad IDs to a JSON file."""
    with open(SEEN_ADS_FILE, "w") as f:
        json.dump(ad_ids, f, indent=4)
    logger.info(f"Successfully saved {len(ad_ids)} ad IDs to {SEEN_ADS_FILE}")

def send_telegram_notification(ad: Dict[str, Any]):
    """Sends a formatted message to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram token or chat ID not set. Skipping notification.")
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
        logger.info(f"Successfully sent notification for ad: {ad['id']}")
    except requests.RequestException as e:
        logger.error(f"Error sending Telegram notification: {e}")

# --- Scraping Functions ---

def scrape_njuskalo(page: Page) -> List[Dict[str, Any]]:
    """Scrapes Njuškalo for apartment listings."""
    logger.info("Scraping Njuškalo...")
    ads = []
    try:
        page.goto(NJUSKALO_URL, wait_until="domcontentloaded", timeout=60000)

        # --- Try to accept cookies ---
        try:
            # Using a selector that is common for cookie banners on Croatian sites
            cookie_button_selector = 'button:has-text("Slažem se")'
            logger.info(f"Looking for cookie consent button: {cookie_button_selector}")
            button = page.locator(cookie_button_selector).first
            # Use a short timeout as the button may not exist
            if button.is_visible(timeout=5000):
                logger.info("Cookie consent button found. Clicking it.")
                button.click()
                page.wait_for_timeout(2000)  # Wait for overlay to disappear
            else:
                logger.info("No cookie consent button was found or visible.")
        except Exception as e:
            logger.warning(f"An error occurred while trying to click cookie button (this is often okay): {e}")
        # --- END ---

        item_selector = ".EntityList-item"  # Use the more general selector
        logger.info(f"Waiting for main ad selector: {item_selector}")
        page.wait_for_selector(item_selector, timeout=30000)

        items = page.query_selector_all(item_selector)
        logger.info(f"Found {len(items)} potential ad items.")
        
        for item in items:
            # Extract ad_id from data-href attribute
            data_href = item.get_attribute("data-href")
            if not data_href:
                continue
            
            # Example: "/nekretnine/ul-brace-domany-8-41-m2-lift-klima-odvojena-spavaca-soba-oglas-47228589"
            # Extracting "47228589"
            ad_id_match = re.search(r'-oglas-(\d+)', data_href)
            if not ad_id_match:
                # Fallback to data-id if data-href doesn't match the pattern
                ad_id = item.get_attribute("data-id")
                if not ad_id:
                    logger.warning(f"Could not extract ad ID from data-href or data-id for item: {data_href}")
                    continue
            else:
                ad_id = ad_id_match.group(1)

            title_element = item.query_selector(".entity-title a")
            price_element = item.query_selector(".entity-prices .price") # More specific selector for price
            description_element = item.query_selector(".entity-description-main")

            title = title_element.inner_text().strip() if title_element else "N/A"
            link = title_element.get_attribute("href") if title_element else "N/A"
            description = description_element.inner_text().strip() if description_element else ""
            
            # Skip if essential info is missing
            if title == "N/A" or link == "N/A":
                logger.warning(f"Skipping ad with missing title/link: {data_href}")
                continue

            if "/nekretnine" not in link:
                logger.debug(f"Skipping non-apartment ad: {link}")
                continue

            if "Trešnjevka" not in description:
                logger.debug(f"Skipping ad outside Trešnjevka: {description}")
                continue

            full_link = f"https://www.njuskalo.hr{link}" if link.startswith('/') else link
            price = price_element.inner_text().strip() if price_element else "N/A"

            ads.append({
                "id": f"njuskalo-{ad_id}",
                "title": title,
                "price": price,
                "link": full_link
            })
    except Exception as e:
        logger.error(f"Error scraping Njuškalo: {e}", exc_info=True)
        page.screenshot(path="error_njuskalo.png")
    
    logger.info(f"Found {len(ads)} ads on Njuškalo.")
    return ads

def scrape_index_oglasi(page: Page) -> List[Dict[str, Any]]:
    """Scrapes Index Oglasi for apartment listings."""
    logger.info("Scraping Index Oglasi...")
    # This selector targets the main <a> tag for each ad, which contains all info.
    # It looks for <a> tags whose href contains the common path for ad listings.
    ad_link_selector = 'a[href*="/oglasi/nekretnine/najam-stanova/oglas/"]'
    ads = []
    try:
        page.goto(INDEX_OGLASI_URL, wait_until="domcontentloaded", timeout=60000)
        
        # --- Try to accept cookies (added for robustness) ---
        try:
            selectors_to_try = [
                'button:has-text("Prihvati sve")', # "Accept all"
                'button:has-text("Prihvaćam")',   # "I accept"
                '#didomi-notice-agree-button',      # A common ID for consent dialogs
                '[id*="cookie"] button',            # Generic cookie button
            ]
            
            clicked = False
            for selector in selectors_to_try:
                logger.info(f"Looking for cookie consent button with selector: {selector}")
                button = page.locator(selector).first
                if button.is_visible(timeout=5000): # Use a short timeout as the button may not exist
                    logger.info("Cookie consent button found. Clicking it.")
                    button.click()
                    page.wait_for_timeout(2000) # Wait for overlay to disappear
                    clicked = True
                    break # Exit loop once clicked
            
            if not clicked:
                logger.info("No common cookie consent button was found or visible.")

        except Exception as e:
            logger.warning(f"An error occurred while trying to click cookie button (this is often okay): {e}")
        # --- END cookie handling ---

        logger.info(f"Waiting for ad links with selector: {ad_link_selector}")
        page.wait_for_selector(ad_link_selector, timeout=30000)

        items = page.query_selector_all(ad_link_selector)
        logger.info(f"Found {len(items)} potential ad links.")
        
        for item in items: # Each 'item' is now the <a> element
            link = item.get_attribute("href")
            
            # Ensure the link is valid and extract ID
            if not link or "/oglasi/" not in link:
                logger.debug(f"Skipping item due to invalid link: {link}")
                continue

            # Extract ID from URL: e.g., /oglasi/.../1234567 -> 1234567
            ad_id = link.split('/')[-1]
            if not ad_id.isdigit():
                 # sometimes the last part is not an id, try one level up
                 ad_id_path_segment = link.rstrip('/').split('/')[-1]
                 if ad_id_path_segment.isdigit():
                     ad_id = ad_id_path_segment
                 else:
                     logger.warning(f"Could not extract digit ID from link: {link}")
                     continue

            title_element = item.query_selector(".AdSummary__title___y1fZw")
            price_element = item.query_selector(".adPrice__price___3o3Dk")
            location_element = item.query_selector(".adLocation__location___3r63d")
            
            title = title_element.inner_text().strip() if title_element else "N/A"
            price = price_element.inner_text().strip() if price_element else "N/A" 
            location = location_element.inner_text().strip() if location_element else "N/A"
            
            # Final check to ensure we extracted something meaningful
            if title == "N/A" and price == "N/A":
                logger.warning(f"Skipping ad with missing title/price: {link}")
                continue

            # Filter for Trešnjevka only because Index Oglasi filtering doesnt work
            if "Trešnjevka" not in location:
                logger.debug(f"Skipping ad outside Trešnjevka: {location}")
                continue

            ads.append({
                "id": f"index-{ad_id}",
                "title": title,
                "price": price,
                "link": link if link.startswith("http") else f"https://www.index.hr{link}"
            })
    except Exception as e:
        logger.error(f"Error scraping Index Oglasi: {e}", exc_info=True)
        page.screenshot(path="error_index_oglasi.png")

    logger.info(f"Found {len(ads)} ads on Index Oglasi.")
    return ads


# --- Main Execution ---

def main():
    """Main function to run the scraper."""
    logger.info("--- Starting scraper run ---")
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        logger.critical("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables. Exiting.")
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
        logger.info("Sleeping for a few seconds before next scrape...")
        time.sleep(random.uniform(3, 7))
        index_ads = scrape_index_oglasi(page)

        all_ads = njuskalo_ads + index_ads

        logger.info(f"Total ads found across all sites: {len(all_ads)}")
        
        # Process ads
        for ad in all_ads:
            if ad["id"] not in seen_ads:
                logger.info(f"New ad found: {ad['id']} - {ad['title']}")
                all_new_ads.append(ad)
                seen_ads.append(ad['id'])

        # Send notifications and save state
        if all_new_ads:
            logger.info(f"Found {len(all_new_ads)} new ads in total. Sending notifications...")
            for ad in reversed(all_new_ads): # Send oldest first
                send_telegram_notification(ad)
                time.sleep(random.uniform(1, 3)) # Avoid rate limiting
            
            save_seen_ads(seen_ads)
        else:
            logger.info("No new ads found.")

        browser.close()
    logger.info("--- Scraper run finished ---")

if __name__ == "__main__":
    main()
