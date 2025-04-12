"""
LinkedIn Bot - Login and Utilities Module
"""
import time
import random
import re
import logging
from typing import List, Set, Dict, Tuple, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException,
    NoSuchElementException,
    TimeoutException,
)
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options


# Configuration


# Logger setup
class LoggerSetup:
    @staticmethod
    def get_logger(name):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        return logging.getLogger(name)


# Utility functions
class Utils:
    @staticmethod
    def random_delay(min_seconds=1, max_seconds=3):
        """Adds random delay to simulate human user behavior"""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)

    @staticmethod
    def random_scroll(driver, min_pixels=100, max_pixels=500):
        """Performs random scrolling on the page"""
        height = random.randint(min_pixels, max_pixels)
        driver.execute_script(f"window.scrollBy(0, {height});")
        time.sleep(random.uniform(0.5, 2.0))

    @staticmethod
    def wait_and_find_element(driver, by, value, timeout=15):
        try:
            return WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
        except Exception as e:
            logger = LoggerSetup.get_logger("Utils")
            logger.error(f"Element {value} not found within {timeout}s: {str(e)}")
            return None

    @staticmethod
    def create_filename_from_query(query):
        """Creates a JSON filename based on the search query"""
        clean_query = re.sub(r'[^\w\s-]', '', query.lower()).strip().replace(' ', '_')
        return f"{clean_query}_linkedin_profiles.json"


# Driver factory
class DriverFactory:
    @staticmethod
    def create_chrome_driver():
        options = Options()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-blink-features")
        options.add_argument('--disable-extensions')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-dev-shm-usage')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # Hide webdriver flag in JS
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Additional automation hiding
        driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: function() { return [1, 2, 3, 4, 5]; }});")
        driver.execute_script("Object.defineProperty(navigator, 'languages', {get: function() { return ['pl-PL', 'pl', 'en-US', 'en']; }});")
        
        return driver


class LinkedInLoginHandler:
    def __init__(self, driver):
        self.driver = driver
        self.logger = LoggerSetup.get_logger("LinkedInLoginHandler")

    def apply_anti_bot_measures(self):
        """Applies additional methods to prevent bot detection after login"""
        self.logger.info("Applying anti-bot detection measures...")
        try:
            # Simulate random interactions
            Utils.random_scroll(self.driver, 200, 500)
            Utils.random_delay(1, 2)
            
            # Additional browser memory modification
            self.driver.execute_script("""
                // Simulate localStorage
                if (!window.localStorage) {
                    Object.defineProperty(window, 'localStorage', {
                        value: {
                            getItem: function(key) { return null; },
                            setItem: function(key, value) { return null; }
                        }
                    });
                }
                
                // Simulate browsing history
                if (window.history) {
                    Object.defineProperty(history, 'length', { value: Math.floor(Math.random() * 20) + 5 });
                }
            """)
            
            # Simulate random mouse movement
            width, height = self.driver.execute_script("return [window.innerWidth, window.innerHeight];")
            x, y = random.randint(100, width - 200), random.randint(100, height - 200)
            self.driver.execute_script(f"document.dispatchEvent(new MouseEvent('mousemove', {{clientX: {x}, clientY: {y}, bubbles: true}}));")
            
            self.logger.info("Anti-bot measures applied successfully")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to apply all anti-bot measures: {e}")
            return False

    def handle_auth_wall(self):
        # Try multiple selectors to find the login button
        selectors = [
            "button.authwall-join-form__form-toggle--bottom",
            "button.sign-in-form__submit-btn",
            "button[data-id='sign-in-form__submit-btn']",
            "//button[contains(text(), 'Zaloguj się')]",
            "//button[contains(text(), 'Sign in')]"
        ]
        
        for selector in selectors:
            try:
                if selector.startswith("//"):
                    login_button = Utils.wait_and_find_element(self.driver, By.XPATH, selector)
                else:
                    login_button = Utils.wait_and_find_element(self.driver, By.CSS_SELECTOR, selector)
                
                if login_button:
                    self.driver.execute_script("arguments[0].click();", login_button)
                    Utils.random_delay(2, 4)
                    return True
            except Exception:
                continue
        
        return False

    def handle_challenge(self):
        self.logger.info("Waiting for potential challenge/captcha resolution...")
        while "challenge" in self.driver.current_url:
            time.sleep(5)
        self.logger.info("Challenge resolved!")

    def login(self, email, password):
        try:
            self.logger.info("Starting login process...")
            
            # Auth wall check
            if "join" in self.driver.current_url or "authwall" in self.driver.page_source:
                self.handle_auth_wall()
    
            # Short delay to ensure page is loaded
            Utils.random_delay(2, 4)
            
            # Find email field - try multiple selectors
            email_selectors = [
                'input[name="session_key"]',
                'input[id="username"]',
                'input[autocomplete="username"]',
                '//input[@type="text"][@id="username"]',
                '//input[contains(@class, "login-email")]'
            ]
            
            # First search for email field and wait until it's interactive
            email_input = None
            for selector in email_selectors:
                try:
                    if selector.startswith("//"):
                        email_input_elem = WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, selector))
                        )
                    else:
                        email_input_elem = WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                    
                    # Make sure the element is visible and can be interacted with
                    if email_input_elem.get_attribute("id"):
                        email_input = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.ID, email_input_elem.get_attribute("id")))
                        )
                    else:
                        email_input = email_input_elem
                    
                    if email_input:
                        self.logger.info(f"Found email field using selector: {selector}")
                        break
                except Exception as e:
                    self.logger.debug(f"Email field not found with selector {selector}: {e}")
                    continue
            
            if not email_input:
                # Last attempt - find any text field
                try:
                    email_input = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//input[@type='text' or @type='email']"))
                    )
                    self.logger.info("Found email field using fallback selector")
                except Exception as e:
                    self.logger.error(f"Could not find email field after multiple attempts: {e}")
                    return False
            
            # Clear field before typing
            email_input.clear()
            
            # Click on field and check if it's active
            self.driver.execute_script("arguments[0].click();", email_input)
            Utils.random_delay(0.5, 1)
            
            # Make sure the field is active before using send_keys
            active_element = self.driver.execute_script("return document.activeElement;")
            if active_element.get_attribute("id") != email_input.get_attribute("id"):
                self.logger.warning("Email field is not active, trying to re-activate")
                self.driver.execute_script("arguments[0].focus();", email_input)
                Utils.random_delay(0.5, 1)
            
            # Type email directly via JavaScript
            self.driver.execute_script(f"arguments[0].value = '{email}';", email_input)
            
            # Simulate change/input event
            self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", email_input)
            self.driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", email_input)
            
            Utils.random_delay(1, 2)
            
            # Find password field - similar approach as for email
            password_selectors = [
                'input[name="session_password"]',
                'input[id="password"]',
                'input[autocomplete="current-password"]',
                '//input[@type="password"]',
                '//input[contains(@class, "login-password")]'
            ]
            
            password_input = None
            for selector in password_selectors:
                try:
                    if selector.startswith("//"):
                        password_input_elem = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.XPATH, selector))
                        )
                    else:
                        password_input_elem = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                    
                    # Make sure the element is visible and can be interacted with
                    if password_input_elem.get_attribute("id"):
                        password_input = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.ID, password_input_elem.get_attribute("id")))
                        )
                    else:
                        password_input = password_input_elem
                    
                    if password_input:
                        self.logger.info(f"Found password field using selector: {selector}")
                        break
                except Exception as e:
                    self.logger.debug(f"Password field not found with selector {selector}: {e}")
                    continue
            
            if not password_input:
                # Last attempt - find any password field
                try:
                    password_input = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//input[@type='password']"))
                    )
                    self.logger.info("Found password field using fallback selector")
                except Exception as e:
                    self.logger.error(f"Could not find password field after multiple attempts: {e}")
                    return False
            
            # Clear field before typing
            password_input.clear()
            
            # Click on field and check if it's active
            self.driver.execute_script("arguments[0].click();", password_input)
            Utils.random_delay(0.5, 1)
            
            # Type password directly via JavaScript
            self.driver.execute_script(f"arguments[0].value = '{password}';", password_input)
            
            # Simulate change/input event
            self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", password_input)
            self.driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", password_input)
            
            Utils.random_delay(1, 2)
    
            # Click 'Login' - try multiple selectors
            submit_selectors = [
                'button[data-id="sign-in-form__submit-btn"]',
                'button.sign-in-form__submit-button',
                'button[type="submit"]',
                '//button[contains(text(), "Zaloguj")]',
                '//button[contains(text(), "Sign in")]'
            ]
            
            submit_button = None
            for selector in submit_selectors:
                try:
                    if selector.startswith("//"):
                        submit_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                    else:
                        submit_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                    
                    if submit_button:
                        self.logger.info(f"Found login button using selector: {selector}")
                        break
                except Exception as e:
                    self.logger.debug(f"Login button not found with selector {selector}: {e}")
                    continue
            
            if not submit_button:
                self.logger.error("Could not find 'Login' button after multiple attempts")
                return False
            
            # Add random delay before clicking
            Utils.random_delay(1, 2)
            
            # Use JavaScript to click the button
            self.driver.execute_script("arguments[0].click();", submit_button)
            self.logger.info("Clicked login button")
            
            # Longer wait for loading after login
            Utils.random_delay(4, 6)
            
            if "challenge" in self.driver.current_url:
                self.handle_challenge()
    
            # Login verification
            is_logged_in = any(marker in self.driver.current_url for marker in ["/feed", "/in/", "mynetwork"])
            
            if is_logged_in:
                self.logger.info("Logged in successfully!")
                
                # Apply anti-bot measures after login
                self.apply_anti_bot_measures()
            else:
                self.logger.error("Login failed. Check credentials or if captcha is required.")
                
            return is_logged_in
            
        except Exception as e:
            self.logger.error(f"Unexpected error during login: {e}")
            return False
            