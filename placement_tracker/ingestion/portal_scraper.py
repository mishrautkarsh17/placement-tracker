from playwright.sync_api import sync_playwright
import logging
from placement_tracker.config import POD_AI_URL

def scrape(pod_ai_username: str, pod_ai_password: str, target_url: str = None) -> list[dict]:
    """
    Scrapes pod.ai Applications or Opportunities page and returns a list of dicts with raw page text.
    Uses full-page-text capture rather than fragile CSS selectors, so it won't
    break when pod.ai updates their frontend.
    """
    if not POD_AI_URL or not pod_ai_username or not pod_ai_password:
        logging.error("Pod.ai credentials/URL not provided.")
        return []

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            logging.info(f"Navigating to {POD_AI_URL}")
            page.goto(POD_AI_URL, wait_until="networkidle", timeout=30000)

            # --- LOGIN ---
            # Try email/password fields
            try:
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                page.wait_for_timeout(2000) # Give React a moment to settle DOM
                
                email_loc = page.locator("input[type='email']")
                email_loc.wait_for(state="visible", timeout=30000)
                email_loc.fill(pod_ai_username)
                
                pwd_loc = page.locator("input[type='password']")
                pwd_loc.wait_for(state="visible", timeout=15000)
                pwd_loc.fill(pod_ai_password)
                
                page.click("button[type='submit']")
                page.wait_for_load_state("networkidle", timeout=20000)
                page.wait_for_timeout(5000)
                logging.info("Login submitted and waited 5s.")
            except Exception as e:
                logging.error(f"Login step failed: {e}")

            # --- NAVIGATE TO TARGET URL ---
            try:
                final_url = target_url if target_url else f"{POD_AI_URL}/d/HjFzVC/applications/"
                logging.info(f"Navigating to {final_url}")
                page.goto(final_url, wait_until="networkidle", timeout=20000)
                logging.info(f"Navigated to target tab: {final_url}")
                
                if not target_url:
                    # Try clicking the Applications sub-tab
                    try:
                        page.locator("text=Applications").first.click(timeout=5000)
                        page.wait_for_load_state("networkidle", timeout=10000)
                        logging.info("Clicked Applications sub-tab.")
                    except Exception:
                        logging.warning("Could not click Applications sub-tab, continuing on Opportunities page.")
            except Exception as e2:
                logging.error(f"Could not reach target tab: {e2}")

            # --- CAPTURE ALL CARD TEXT DURING SCROLL ---
            # Pod.ai uses React Virtualization. If we just scroll to the bottom, the top cards 
            # disappear from the DOM. We must collect cards continuously while scrolling.
            unique_cards = set()
            
            selectors_to_try = [
                "div.MuiCard-root",
                "div:has(> * > text='Job type')",
                "div:has-text('Job type')",
                "li:has-text('Stipend')",
                "[class*='item']:has-text('Job type')",
                "div:has(> * > text='CTC')",
            ]

            for _ in range(25):
                # Wait for any new cards to render after scroll
                page.wait_for_timeout(1000)
                
                found_cards_in_dom = False
                for sel in selectors_to_try:
                    try:
                        count = page.locator(sel).count()
                        if count > 0:
                            found_cards_in_dom = True
                            blocks = page.locator(sel).all()
                            for b in blocks:
                                txt = b.inner_text().strip()
                                if txt:
                                    unique_cards.add(txt)
                            break # Found cards with this selector, skip other selectors
                    except Exception:
                        continue
                
                # If no cards found at all, try grabbing the whole body text
                if not found_cards_in_dom:
                    try:
                        body_text = page.locator("main, #main, [role='main'], body").first.inner_text()
                        if body_text:
                            unique_cards.add(body_text)
                    except Exception:
                        pass
                
                # Scroll down
                page.keyboard.press("End")

            # Convert our unique captured texts back into the results format
            for txt in unique_cards:
                # If it's a huge block of text (fallback), mark it as bulk
                if len(txt) > 2000:
                    results.append({"raw_card_text": txt, "bulk": True})
                else:
                    results.append({"raw_card_text": txt})

        except Exception as e:
            logging.error(f"Error during pod.ai scraping: {e}")
        finally:
            browser.close()

    logging.info(f"Scraper returning {len(results)} card(s).")
    return results
