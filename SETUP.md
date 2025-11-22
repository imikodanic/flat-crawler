# Setup Instructions for Apartment Scraper

This document outlines the steps required to set up and run the apartment scraping automation using GitHub Actions and Telegram notifications.

## 1. GitHub Repository Secrets

You need to add the following secrets to your GitHub repository. These secrets will be used by the GitHub Actions workflow to send notifications to your Telegram chat.

To add secrets:
1. Go to your GitHub repository.
2. Click on "Settings" (usually found in the top right).
3. In the left sidebar, navigate to "Security" > "Secrets and variables" > "Actions".
4. Click on "New repository secret".

Add the following two secrets:

-   **`TELEGRAM_BOT_TOKEN`**:
    *   **How to get it:**
        1.  Open Telegram and search for `@BotFather`.
        2.  Start a chat with `@BotFather` and send the command `/newbot`.
        3.  Follow the instructions to choose a name and username for your new bot.
        4.  `@BotFather` will give you an HTTP API token. This is your `TELEGRAM_BOT_TOKEN`.

-   **`TELEGRAM_CHAT_ID`**:
    *   **How to get it:**
        1.  After creating your bot, search for your new bot by its username in Telegram and start a chat with it. Send any message to your bot (e.g., "Hi").
        2.  Open your web browser and go to `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates` (replace `<YOUR_BOT_TOKEN>` with your actual bot token).
        3.  Look for a JSON object containing `"chat":{"id":...}`. The number after `"id":` is your `TELEGRAM_CHAT_ID`. It will usually be a negative number if it's a group chat.
        4.  If you want to send messages to a group, add your bot to the group and make it an administrator. Then send a message to the group and refresh the `getUpdates` URL.

## 2. Obtaining Njuškalo and Index Oglasi URLs

The `main.py` script requires specific URLs for Njuškalo and Index Oglasi that are pre-filtered and sorted by the newest listings.

### General Steps:
1.  Go to the respective website (Njuškalo or Index Oglasi).
2.  Apply your desired filters (e.g., location like "Zagreb", specific neighborhoods like "Trešnjevka", maximum price, number of rooms, etc.).
3.  **Crucially, ensure the results are sorted by "Newest first" or "Latest listings".**
4.  Copy the URL from your browser's address bar.

### Examples:

-   **Njuškalo (Example: Zagreb, Max Price 600 EUR, Sorted by Newest)**
    1.  Go to [Njuškalo Real Estate](https://www.njuskalo.hr/nekretnine).
    2.  Select "Iznajmljivanje stanova" (Apartment Rentals).
    3.  Enter "Zagreb" as the location.
    4.  Set "Cijena do" (Price up to) to `600`.
    5.  Find the sorting option (usually a dropdown) and select "Najnovije" (Newest).
    6.  The URL in your browser might look something like: `https://www.njuskalo.hr/iznajmljivanje-stanova/zagreb?price[max]=600&sort=new`
    7.  Update the `NJUSKALO_URL` variable in `main.py` with this URL.

-   **Index Oglasi (Example: Zagreb, Max Price 600 EUR, Sorted by Newest)**
    1.  Go to [Index Oglasi Real Estate](https://www.index.hr/oglasi/stanovi/najam).
    2.  Select "Najam" (Rentals).
    3.  Enter "Zagreb" as the city.
    4.  Set "Maks. cijena" (Max Price) to `600`.
    5.  Find the sorting option (usually a dropdown or button) and select "Najnovije" (Newest). This might append `&sort=1` or similar to the URL.
    6.  The URL in your browser might look something like: `https://www.index.hr/oglasi/najam-stanova/grad-zagreb?pojam=&maxCIjena=600&tipoglasa=1&sort=1`
    7.  Update the `INDEX_OGLASI_URL` variable in `main.py` with this URL.

Make sure to replace the placeholder URLs in `main.py` with your custom, filtered, and sorted URLs before running the workflow.

## 3. Running the GitHub Action

The GitHub Action is configured to run automatically every 15 minutes. You can also trigger it manually:

1.  Go to your GitHub repository.
2.  Click on "Actions".
3.  In the left sidebar, click on "Oglasnik Scraper" (the name of the workflow).
4.  Click on the "Run workflow" dropdown button on the right.
5.  Click "Run workflow" again.

The workflow will then execute, scrape for new ads, send Telegram notifications, and commit any changes to `seen_ads.json` back to your repository.