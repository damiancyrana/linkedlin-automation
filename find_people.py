"""
LinkedIn Bot - People Search Module
"""
import json
import os
import re
import random
import time
from typing import Set

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

from login import LoggerSetup, Utils


class LinkedInPeopleSearchHandler:
    def __init__(self, driver, search_query):
        self.driver = driver
        self.profiles = []
        self.search_query = search_query
        self.json_filename = Utils.create_filename_from_query(search_query)
        self.json_initialized = False
        self.discovered_profile_selector = None
        self.discovered_title_selector = None
        self.discovered_location_selector = None
        self.discovered_summary_selector = None
        self.logger = LoggerSetup.get_logger("LinkedInPeopleSearchHandler")

    def discover_selectors(self):
        """Dynamically discovers selectors for profile elements"""
        self.logger.info("Attempting to automatically discover selectors...")
        
        try:
            # First wait for results to load
            results_container = Utils.wait_and_find_element(
                self.driver,
                By.CSS_SELECTOR,
                "ul[class*='list-style-none']",
                timeout=10
            )
            
            if not results_container:
                self.logger.error("Search results container not found")
                return False
                
            # 1. Find li elements containing links to profiles
            profile_elements = self.driver.find_elements(By.XPATH, "//li[.//a[contains(@href, '/in/')]]")
            
            # If no profiles, try another method
            if not profile_elements or len(profile_elements) == 0:
                self.logger.warning("No profiles found using standard method, trying alternative selectors")
                
                # Alternative approach - find li elements in results container
                profile_elements = results_container.find_elements(By.XPATH, ".//li")
                
                # One more alternative - look for div elements with profile links
                if not profile_elements or len(profile_elements) == 0:
                    profile_elements = self.driver.find_elements(By.XPATH, "//div[.//a[contains(@href, '/in/')]]")
            
            if profile_elements and len(profile_elements) > 0:
                self.logger.info(f"Found {len(profile_elements)} potential profile elements")
                
                # Take first profile element
                sample_profile = profile_elements[0]
                
                # Get class of first element
                profile_class = sample_profile.get_attribute('class')
                if profile_class:
                    classes = profile_class.split()
                    if classes:
                        self.discovered_profile_selector = f"li.{classes[0]}"
                        self.logger.info(f"Detected profile selector: {self.discovered_profile_selector}")
                
                # Analyze profile structure to identify key elements
                # Check potential title/position elements
                title_candidates = sample_profile.find_elements(By.XPATH, ".//div[contains(@class, 't-black')]")
                location_candidates = sample_profile.find_elements(By.XPATH, ".//div[contains(@class, 't-normal')]")
                summary_candidates = sample_profile.find_elements(By.XPATH, ".//p[contains(@class, 't-12') or contains(@class, 'entity-result__summary')]")
                
                # Save full text of first profile for analysis
                self.logger.info(f"First profile text: {sample_profile.text}")
                
                # Title elements analysis
                if title_candidates and len(title_candidates) > 0:
                    title_class = title_candidates[0].get_attribute('class')
                    title_text = title_candidates[0].text
                    self.logger.info(f"Potential title element: {title_text}")
                    self.logger.info(f"Title element class: {title_class}")
                    
                    if title_class:
                        classes = title_class.split()
                        if classes:
                            self.discovered_title_selector = f"div.{classes[0]}"
                            self.logger.info(f"Detected title selector: {self.discovered_title_selector}")
                
                # Location elements analysis
                if location_candidates and len(location_candidates) > 1:
                    location_class = location_candidates[1].get_attribute('class')
                    location_text = location_candidates[1].text
                    self.logger.info(f"Potential location element: {location_text}")
                    self.logger.info(f"Location element class: {location_class}")
                    
                    if location_class:
                        classes = location_class.split()
                        if classes:
                            self.discovered_location_selector = f"div.{classes[0]}"
                            self.logger.info(f"Detected location selector: {self.discovered_location_selector}")
                
                # Summary elements analysis
                if summary_candidates and len(summary_candidates) > 0:
                    summary_class = summary_candidates[0].get_attribute('class')
                    summary_text = summary_candidates[0].text
                    self.logger.info(f"Potential summary element: {summary_text}")
                    self.logger.info(f"Summary element class: {summary_class}")
                    
                    if summary_class:
                        classes = summary_class.split()
                        if classes:
                            self.discovered_summary_selector = f"p.{classes[0]}"
                            self.logger.info(f"Detected summary selector: {self.discovered_summary_selector}")
                        
                return True
            else:
                self.logger.error("No profile elements found during selector discovery")
                return False
            
        except Exception as e:
            self.logger.error(f"Error during selector discovery: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False

    def find_elements_with_retry(self, strategies):
        """Tries different strategies for finding elements"""
        for strategy_name, by_method, selector in strategies:
            try:
                if not selector:
                    continue
                    
                elements = self.driver.find_elements(by_method, selector)
                if elements and len(elements) > 0:
                    self.logger.info(f"Found elements using strategy: {strategy_name}")
                    return elements
            except Exception as e:
                self.logger.debug(f"Failed to find elements with strategy {strategy_name}: {e}")
                continue
        return []

    def extract_text_pattern(self, element_text, pattern_list, default=""):
        """Extracts text matching one of the patterns from the full element text"""
        if not element_text:
            return default
            
        # Search each pattern in text
        for pattern in pattern_list:
            match = re.search(pattern, element_text)
            if match:
                return match.group(1) if match.groups() else match.group(0)
        
        return default

    def extract_profile_data(self, profile_element):
        """Extracts profile data from li element - with adaptive approach"""
        profile_data = {
            "name": "",
            "title": "",
            "location": "",
            "current_company": "",
            "profile_url": ""
        }
        
        try:
            # Get full text of profile element for analysis
            full_element_text = profile_element.text
            self.logger.debug(f"Analyzing profile with text: {full_element_text}")
            
            # 1. Find name and profile address
            name_elements = profile_element.find_elements(By.XPATH, ".//a[contains(@href, '/in/')]")
            
            for name_element in name_elements:
                element_text = name_element.text
                element_href = name_element.get_attribute("href")
                
                if element_text and element_href and '/in/' in element_href:
                    name_text = re.sub(r'Wyświetl profil użytkownika\s+', '', element_text)
                    name_text = re.sub(r'[•]\s+\d+\.\s+.*$', '', name_text).strip()
                    name_text = re.sub(r'<[^>]+>', '', name_text).strip()
                    
                    profile_data["name"] = name_text
                    profile_data["profile_url"] = element_href.split("?")[0]
                    break
            
            # 2. Extract title/position - improved algorithm
            
            # Method 1: Try direct search by classes t-14 + t-black + t-normal
            title_elements = profile_element.find_elements(By.XPATH, 
                ".//div[contains(@class, 't-14') and contains(@class, 't-black') and contains(@class, 't-normal')]")
            
            if title_elements and len(title_elements) > 0:
                for elem in title_elements:
                    text = elem.text.strip()
                    # Make sure found text isn't the same as name
                    if text and text != profile_data["name"]:
                        profile_data["title"] = text
                        break
            
            # Method 2: Use discovered selector if title still not found
            if not profile_data["title"] and self.discovered_title_selector:
                try:
                    title_elements = profile_element.find_elements(By.CSS_SELECTOR, self.discovered_title_selector)
                    if title_elements and len(title_elements) > 0:
                        text = title_elements[0].text.strip()
                        if text and text != profile_data["name"]:
                            profile_data["title"] = text
                except Exception as e:
                    self.logger.debug(f"Error using discovered_title_selector: {e}")
            
            # Method 3: Search by keywords related to positions
            if not profile_data["title"] or profile_data["title"] == profile_data["name"]:
                keyword_elements = profile_element.find_elements(By.XPATH,
                    ".//div[contains(text(), 'Engineer') or contains(text(), 'Developer') or contains(text(), 'Security') or contains(text(), 'Analyst') or contains(text(), 'Manager')]")
                
                if keyword_elements and len(keyword_elements) > 0:
                    for elem in keyword_elements:
                        text = elem.text.strip()
                        if text and text != profile_data["name"] and "Kontakt" not in text and "Zobacz" not in text:
                            profile_data["title"] = text
                            break
            
            # 3. Extract location - unchanged
            if self.discovered_location_selector:
                try:
                    location_elements = profile_element.find_elements(By.CSS_SELECTOR, self.discovered_location_selector)
                    if location_elements and len(location_elements) > 0:
                        profile_data["location"] = location_elements[0].text.strip()
                except Exception as e:
                    self.logger.debug(f"Error using discovered_location_selector: {e}")
            
            # 4. Extract current company - improved
            if self.discovered_summary_selector:
                try:
                    summary_elements = profile_element.find_elements(By.CSS_SELECTOR, self.discovered_summary_selector)
                    if summary_elements and len(summary_elements) > 0:
                        summary_text = summary_elements[0].text
                        
                        # Improved regex to extract company name
                        company_match = re.search(r'Obecnie:.*?\s+w\s+([^•\n]+)', summary_text, re.IGNORECASE)
                        if company_match:
                            profile_data["current_company"] = company_match.group(1).strip()
                        else:
                            # Alternative pattern
                            company_match = re.search(r'Obecnie:.*?([A-Z][a-zA-Z0-9\s]+)$', summary_text)
                            if company_match:
                                profile_data["current_company"] = company_match.group(1).strip()
                except Exception as e:
                    self.logger.debug(f"Error using discovered_summary_selector: {e}")
            
            # Final data cleaning
            for key in profile_data:
                if profile_data[key]:
                    profile_data[key] = re.sub(r'\n.*$', '', profile_data[key]).strip()
                    profile_data[key] = re.sub(r'<[^>]+>', '', profile_data[key]).strip()
            
            # Final verification - make sure title isn't name
            if profile_data["title"] == profile_data["name"]:
                profile_data["title"] = ""
                
            self.logger.debug(f"Extracted profile data: {profile_data}")
            
        except Exception as e:
            self.logger.warning(f"Error extracting profile data: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            
        return profile_data

    def init_json_file(self):
        """Initializes JSON file with empty array"""
        if not self.json_initialized:
            with open(self.json_filename, 'w', encoding='utf-8') as jsonfile:
                json.dump([], jsonfile)
            
            self.json_initialized = True
            self.logger.info(f"Initialized JSON file: {self.json_filename}")

    def append_profile_to_json(self, profile):
        """Adds a single profile to JSON file"""
        try:
            # Read current data
            profiles = []
            if os.path.exists(self.json_filename) and os.path.getsize(self.json_filename) > 0:
                with open(self.json_filename, 'r', encoding='utf-8') as jsonfile:
                    profiles = json.load(jsonfile)
            
            # Add new profile
            profiles.append(profile)
            
            # Save updated data
            with open(self.json_filename, 'w', encoding='utf-8') as jsonfile:
                json.dump(profiles, jsonfile, ensure_ascii=False, indent=2)
                
            self.logger.info(f"Added to JSON: {profile['name']} - {profile['title']}")
        except Exception as e:
            self.logger.error(f"Error saving to JSON: {e}")
        
    def process_search_results_page(self):
        """Processes search results page and collects profile data"""
        self.logger.info("Processing search results page")
        
        # Wait for results to load
        Utils.wait_and_find_element(
            self.driver, 
            By.CSS_SELECTOR, 
            "ul[class*='list-style-none']"
        )
        
        Utils.random_delay(2, 3)
        
        # Initialize JSON file if not exists
        if not self.json_initialized:
            self.init_json_file()
        
        # Find all profile elements on page
        profile_strategies = [
            ("Discovered selector", By.CSS_SELECTOR, self.discovered_profile_selector),
            ("Li elements with profile links", By.XPATH, "//li[.//a[contains(@href, '/in/')]]"),
            ("Li elements containing keywords", By.XPATH, "//li[contains(., 'Security') or contains(., 'Engineer') or contains(., 'Architect')]"),
            ("Li elements as ul children", By.CSS_SELECTOR, "ul[class*='list-style-none'] > li"),
            ("Div elements with profile links", By.XPATH, "//div[.//a[contains(@href, '/in/')]]")
        ]
        
        # Find profile elements using different strategies
        profile_elements = self.find_elements_with_retry(profile_strategies)
        
        if not profile_elements or len(profile_elements) == 0:
            self.logger.error("No profile elements found on page")
            return []
        
        self.logger.info(f"Found {len(profile_elements)} potential profile elements")
        
        # Display full text of first element for analysis
        if profile_elements and len(profile_elements) > 0:
            self.logger.info(f"First profile element text: {profile_elements[0].text}")
        
        profiles_found = []
        
        for i, profile_element in enumerate(profile_elements):
            try:
                # Check if element is actually a person profile (not an ad or other element)
                element_text = profile_element.text.lower()
                
                # Skip elements that are ads or other elements, not profiles
                if any(keyword in element_text for keyword in ["premium", "reaktywuj", "reactivate", "anuluj w dowolnym momencie"]):
                    self.logger.debug(f"Skipping element {i+1}, probably an ad")
                    continue
                
                # Check presence of profile link - most reliable verification method
                try:
                    profile_link = profile_element.find_element(By.XPATH, ".//a[contains(@href, '/in/')]")
                    if not profile_link:
                        self.logger.debug(f"Skipping element {i+1}, no profile link")
                        continue
                except Exception:
                    self.logger.debug(f"Skipping element {i+1}, couldn't find profile link")
                    continue
                    
                # Extract profile data
                profile_data = self.extract_profile_data(profile_element)
                
                # Add only if name and profile link were extracted
                if profile_data["name"] or profile_data["profile_url"]:  
                    profiles_found.append(profile_data)
                    # Immediately save to JSON
                    self.append_profile_to_json(profile_data)
                    self.logger.info(f"Found profile: {profile_data['name']} - {profile_data['title']}")
                    
                    # Add random page scrolling for better human simulation
                    if random.random() < 0.3:  # 30% chance to scroll after each profile
                        Utils.random_scroll(self.driver)
                else:
                    self.logger.debug(f"Skipping element {i+1}, couldn't extract basic profile data")
                        
            except StaleElementReferenceException:
                self.logger.warning(f"Element {i+1} became stale, skipping")
                continue
            except Exception as e:
                self.logger.warning(f"Error processing profile {i+1}: {e}")
                import traceback
                self.logger.debug(traceback.format_exc())
                
        self.logger.info(f"Found {len(profiles_found)} profiles on page")
        return profiles_found

    def navigate_to_next_page(self):
        """Navigates to next page of results, if available."""
        try:
            # First wait for pagination to load - use different selectors
            pagination_selectors = [
                ".artdeco-pagination",
                "div.artdeco-pagination",
                "//div[contains(@class, 'artdeco-pagination')]",
                "//div[contains(@class, 'pagination')]"
            ]
            
            pagination = None
            for selector in pagination_selectors:
                try:
                    if selector.startswith("//"):
                        pagination = WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, selector))
                        )
                    else:
                        pagination = WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                    
                    if pagination:
                        break
                except TimeoutException:
                    continue
            
            if not pagination:
                self.logger.warning("Pagination not found on page")
                return False
            
            # Scroll to pagination
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", pagination)
            Utils.random_delay(1, 2)
            
            # Find "Next" button using different selectors
            next_button_strategies = [
                ("artdeco-pagination__button--next class", By.XPATH, "//button[contains(@class, 'artdeco-pagination__button--next')]"),
                ("Aria-label containing 'Next'", By.XPATH, "//button[contains(@aria-label, 'Next') or contains(@aria-label, 'Dalej')]"),
                ("Button with right arrow icon", By.XPATH, "//button[.//li-icon[@type='chevron-right']]"),
                ("CSS selector for Next button", By.CSS_SELECTOR, "button.artdeco-pagination__button--next"),
                ("'Next' text in button", By.XPATH, "//button[contains(text(), 'Dalej') or contains(text(), 'Next')]"),
                ("Last pagination button", By.XPATH, "//div[contains(@class, 'artdeco-pagination')]//button[last()]")
            ]
            
            next_button = None
            for strategy_name, by_method, selector in next_button_strategies:
                try:
                    elements = self.driver.find_elements(by_method, selector)
                    if elements:
                        next_button = elements[0]
                        self.logger.info(f"Found 'Next' button using strategy: {strategy_name}")
                        break
                except Exception:
                    continue
            
            if not next_button:
                self.logger.info("'Next' button not found - reached last page")
                return False
            
            # Check if button is disabled
            button_classes = next_button.get_attribute("class") or ""
            button_disabled = next_button.get_attribute("disabled")
            
            if "disabled" in button_classes or "artdeco-button--disabled" in button_classes or button_disabled:
                self.logger.info("'Next' button is disabled - reached last page")
                return False
                
            self.logger.info("Moving to next page...")
            # First scroll to button
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
            Utils.random_delay(1, 2)
            
            # Save URL before clicking
            current_url = self.driver.current_url
            
            # Click using JavaScript (more reliable)
            self.driver.execute_script("arguments[0].click();", next_button)
            
            # Wait for page refresh
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.staleness_of(pagination)
                )
            except TimeoutException:
                # If page change not detected, check if URL changed
                new_url = self.driver.current_url
                if new_url != current_url:
                    self.logger.info("Navigation to next page confirmed by URL change")
                else:
                    self.logger.warning("Page change not detected, checking other indicators")
                    
                    # Check if page parameter in URL changed
                    if "page=" in new_url:
                        current_page_match = re.search(r'page=(\d+)', current_url)
                        new_page_match = re.search(r'page=(\d+)', new_url)
                        
                        if current_page_match and new_page_match:
                            current_page = int(current_page_match.group(1))
                            new_page = int(new_page_match.group(1))
                            
                            if new_page > current_page:
                                self.logger.info(f"Navigation from page {current_page} to {new_page}")
                            else:
                                self.logger.warning(f"Attempt to go to page {new_page}, but already on page {current_page}")
                    else:
                        self.logger.warning("Could not confirm navigation to next page")
            
            # Wait for results to reload
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "ul[class*='list-style-none']"))
                )
            except TimeoutException:
                self.logger.warning("Results list not detected on new page")
            
            # Add random delay with random scrolling for better simulation
            Utils.random_delay(3, 5)
            Utils.random_scroll(self.driver)
            return True
                
        except Exception as e:
            self.logger.error(f"Problem navigating to next page: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            
            # Add retry with different method
            try:
                # Try navigation directly via URL
                current_url = self.driver.current_url
                if "page=" in current_url:
                    # Increase page number in URL
                    current_page = re.search(r'page=(\d+)', current_url)
                    if current_page:
                        next_page = int(current_page.group(1)) + 1
                        next_url = re.sub(r'page=\d+', f'page={next_page}', current_url)
                        self.logger.info(f"Attempting direct navigation to URL: {next_url}")
                        self.driver.get(next_url)
                        Utils.random_delay(3, 5)
                        return True
                else:
                    # Add page=2 parameter to URL
                    separator = "&" if "?" in current_url else "?"
                    next_url = f"{current_url}{separator}page=2"
                    self.logger.info(f"Attempting direct navigation to URL: {next_url}")
                    self.driver.get(next_url)
                    Utils.random_delay(3, 5)
                    return True
            except Exception as e2:
                self.logger.error(f"Alternative navigation method also failed: {e2}")
                return False

    def get_total_pages(self):
        """Tries to read total number of result pages"""
        try:
            # First try to find number of results information
            total_results_selectors = [
                "//h2[contains(@class, 't-14') and contains(text(), 'wyników')]",
                "//div[contains(text(), 'Około') and contains(text(), 'wyników')]",
                "//div[contains(text(), 'About') and contains(text(), 'results')]",
                "//span[contains(text(), 'wyników')]",
                "//div[contains(@class, 't-14')][contains(text(), 'wyników')]"
            ]
            
            total_results_text = None
            for selector in total_results_selectors:
                try:
                    element = self.driver.find_element(By.XPATH, selector)
                    if element:
                        total_results_text = element.text
                        break
                except Exception:
                    continue
            
            if total_results_text:
                # Extract number of results
                match = re.search(r'(\d+[\s,.]*\d*)\s+wyników', total_results_text)
                if not match:
                    match = re.search(r'About\s+(\d+[\s,.]*\d*)\s+results', total_results_text)
                
                if match:
                    # Remove non-digit characters
                    results_count_str = re.sub(r'[^\d]', '', match.group(1))
                    try:
                        total_results = int(results_count_str)
                        # Assume 10 results per page
                        return max(1, int(total_results / 10) + (1 if total_results % 10 > 0 else 0))
                    except ValueError:
                        pass
            
            # Try different selectors for pagination state
            pagination_state_selectors = [
                "div.artdeco-pagination__page-state",
                "//div[contains(@class, 'pagination') and contains(@class, 'page-state')]",
                "//span[contains(text(), 'Strona') or contains(text(), 'Page')]",
                "//div[contains(@class, 'pagination')]//span[contains(text(), 'z') or contains(text(), 'of')]"
            ]
            
            for selector in pagination_state_selectors:
                try:
                    if selector.startswith("//"):
                        pagination_text = self.driver.find_element(By.XPATH, selector).text
                    else:
                        pagination_text = self.driver.find_element(By.CSS_SELECTOR, selector).text
                    
                    # Search for patterns like "Page X of Y" or "Strona X z Y"
                    match = re.search(r'(?:[Ss]trona|[Pp]age)\s+\d+\s+(?:z|of)\s+(\d+)', pagination_text)
                    if match:
                        return int(match.group(1))
                    
                    # Check other possible formats
                    if "z" in pagination_text:
                        parts = pagination_text.split("z")
                        if len(parts) >= 2:
                            try:
                                return int(parts[1].strip())
                            except ValueError:
                                pass
                    
                    if "of" in pagination_text:
                        parts = pagination_text.split("of")
                        if len(parts) >= 2:
                            try:
                                return int(parts[1].strip())
                            except ValueError:
                                pass
                except Exception:
                    continue
            
            # If reading failed, check number of pagination buttons
            pagination_buttons = self.driver.find_elements(By.CSS_SELECTOR, "button[data-test-pagination-page-btn]")
            if pagination_buttons:
                # Get last visible page number
                last_page_button = pagination_buttons[-1]
                try:
                    return int(last_page_button.text.strip())
                except ValueError:
                    pass
            
            # Default value if can't read
            return 100
                
        except Exception as e:
            self.logger.warning(f"Failed to read number of pages: {e}")
            return 100  # Default value if can't read
            
    def search_and_collect_profiles(self):
        """Searches for profiles and collects data from all available pages"""
        if not self.search_people(self.search_query):
            self.logger.error("Failed to search for people")
            return []
            
        all_profiles = []
        current_page = 1
        total_pages = self.get_total_pages()
        max_pages = min(total_pages, 100)  # Page limit for safety
        
        self.logger.info(f"Found a total of {total_pages} result pages (processing max {max_pages})")
        
        while current_page <= max_pages:
            self.logger.info(f"Processing page {current_page} of {total_pages}")
            
            # Add random delay before processing each page
            Utils.random_delay(1, 3)
            
            # Get profiles from current page
            page_profiles = self.process_search_results_page()
            all_profiles.extend(page_profiles)
            
            self.logger.info(f"Found {len(page_profiles)} profiles on page {current_page}")
            
            # If no profiles found on page, try again with delay
            if len(page_profiles) == 0:
                self.logger.warning(f"No profiles found on page {current_page}, refreshing and retrying")
                self.driver.refresh()
                Utils.random_delay(5, 8)
                
                # Try again
                page_profiles = self.process_search_results_page()
                all_profiles.extend(page_profiles)
                
                # If still no results, break loop
                if len(page_profiles) == 0:
                    self.logger.error("Still no profiles after retry, ending processing")
                    break
            
            # Go to next page
            if current_page < max_pages:
                if not self.navigate_to_next_page():
                    self.logger.info("Can't go to next page - end of processing")
                    break
                
                current_page += 1
                
                # Add random delay between pages
                Utils.random_delay(3, 7)
            else:
                break
                
        self.logger.info(f"Collected data for {len(all_profiles)} profiles from {current_page} pages")
        self.logger.info(f"All data saved to file {self.json_filename}")
        return all_profiles

    def search_people(self, search_query):
        """Performs people search on LinkedIn"""
        self.logger.info(f"Searching for people with query: '{search_query}'")
        
        # Go to LinkedIn home page
        self.driver.get("https://www.linkedin.com/")
        Utils.random_delay(2, 4)
        
        # Find search field - try multiple selectors
        search_input_selectors = [
            "input.search-global-typeahead__input",
            "input[placeholder*='Szukaj']",
            "input[placeholder*='Search']",
            "input[role='combobox']",
            "//input[contains(@class, 'search')]",
            "//input[contains(@placeholder, 'Szukaj') or contains(@placeholder, 'Search')]"
        ]
        
        search_input = None
        for selector in search_input_selectors:
            try:
                if selector.startswith("//"):
                    search_input = Utils.wait_and_find_element(self.driver, By.XPATH, selector, timeout=5)
                else:
                    search_input = Utils.wait_and_find_element(self.driver, By.CSS_SELECTOR, selector, timeout=5)
                
                if search_input:
                    break
            except Exception:
                continue
        
        if not search_input:
            self.logger.error("Search field not found")
            return False
        
        # Clear field and type query in human-like way
        search_input.clear()
        
        # Type one character at a time with random delays
        for char in search_query:
            search_input.send_keys(char)
            time.sleep(random.uniform(0.05, 0.2))
            
        Utils.random_delay(0.5, 1.5)
        search_input.send_keys(Keys.ENTER)
        Utils.random_delay(2, 4)
        
        # Add random page scrolling
        Utils.random_scroll(self.driver)
        
        # Try to navigate to people search results
        try:
            # Navigate to people search results (if not already there)
            people_results_selectors = [
                "//a[contains(text(), 'Zobacz wszystkie wyniki osób')]",
                "//a[contains(text(), 'See all people results')]",
                "//a[contains(text(), 'wszystkie wyniki') and contains(text(), 'osób')]",
                "//a[contains(@href, '/search/results/people')]",
                "//button[contains(text(), 'Osoby')]",
                "//button[contains(text(), 'People')]"
            ]
            
            found_link = False
            for selector in people_results_selectors:
                try:
                    people_link = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    self.driver.execute_script("arguments[0].click();", people_link)
                    Utils.random_delay(2, 4)
                    found_link = True
                    break
                except Exception:
                    continue
                    
            if not found_link:
                # Check if already on people results page
                if "search/results/people" not in self.driver.current_url:
                    self.logger.warning("Link to people results not found")
        except Exception as e:
            self.logger.warning(f"Error navigating to people results: {e}")
        
        # Check URL to confirm
        is_people_results = "search/results/people" in self.driver.current_url
        
        if is_people_results:
            self.logger.info("Successfully navigated to people search results")
            
            # Detect selectors on current page
            self.discover_selectors()
        else:
            self.logger.error("Failed to navigate to people search results")
            
        return is_people_results
    