"""
LinkedIn Bot - Comments Deletion Module
"""
import re
import time
from typing import Set

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException

from login import Config, LoggerSetup, Utils


class LinkedInCommentHandler:
    def __init__(self, driver):
        self.driver = driver
        self.logger = LoggerSetup.get_logger("LinkedInCommentHandler")

    def expand_replies(self):
        # More general XPath selector for "See more replies" buttons
        more_replies_buttons_xpath = "//button[contains(text(), 'Zobacz więcej') or contains(text(), 'więcej odpowiedzi') or contains(text(), 'Show more') or contains(text(), 'more replies')]"
        more_replies_buttons = self.driver.find_elements(By.XPATH, more_replies_buttons_xpath)
        
        for btn in more_replies_buttons:
            try:
                self.driver.execute_script("arguments[0].click();", btn)
                Utils.random_delay(1, 2)
            except Exception as e:
                self.logger.debug(f"Failed to click 'See more replies' button: {e}")

        # More general XPath selector for "See previous replies" buttons
        prev_replies_buttons_xpath = "//button[contains(text(), 'Zobacz poprzednie') or contains(text(), 'poprzednie odpowiedzi') or contains(text(), 'Show previous') or contains(text(), 'previous replies')]"
        prev_replies_buttons = self.driver.find_elements(By.XPATH, prev_replies_buttons_xpath)
        
        for btn in prev_replies_buttons:
            try:
                self.driver.execute_script("arguments[0].click();", btn)
                Utils.random_delay(1.5, 2.5)
            except Exception as e:
                self.logger.debug(f"Failed to click 'See previous replies' button: {e}")

    def load_all_pages(self):
        while True:
            self.expand_replies()
            
            # More general approach to finding "Show more" button
            load_more_selectors = [
                ".scaffold-finite-scroll__load-button",
                "button.scaffold-finite-scroll__load-button",
                "//button[contains(text(), 'Pokaż więcej') or contains(text(), 'Show more') or contains(text(), 'Load more')]"
            ]
            
            load_more_button = None
            for selector in load_more_selectors:
                try:
                    if selector.startswith("//"):
                        elements = self.driver.find_elements(By.XPATH, selector)
                    else:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    if elements:
                        load_more_button = elements[0]
                        break
                except Exception:
                    continue
            
            if load_more_button:
                try:
                    # Scroll to button
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", load_more_button)
                    Utils.random_delay(0.5, 1)
                    
                    # Click button
                    self.driver.execute_script("arguments[0].click();", load_more_button)
                    Utils.random_delay(1.5, 2.5)
                    
                    # Add random page scrolling for better human simulation
                    Utils.random_scroll(self.driver)
                except Exception as e:
                    self.logger.warning(f"Failed to click 'Show more results': {e}")
                    break
            else:
                break

    def find_comments_container(self):
        """Finds the comments container using multiple strategies"""
        container_selectors = [
            "div.scaffold-finite-scroll__content",
            "div[class*='comments-container']",
            "div[data-test-id='comments-container']",
            "//div[contains(@class, 'scaffold-finite-scroll__content')]",
            "//div[contains(@class, 'comments-container')]"
        ]
        
        for selector in container_selectors:
            try:
                if selector.startswith("//"):
                    container = Utils.wait_and_find_element(self.driver, By.XPATH, selector, timeout=5)
                else:
                    container = Utils.wait_and_find_element(self.driver, By.CSS_SELECTOR, selector, timeout=5)
                
                if container:
                    return container
            except Exception:
                continue
        
        return None

    def gather_damian_comment_ids(self) -> Set[str]:
        comment_ids = set()
        self.load_all_pages()

        # Find comments container
        container = self.find_comments_container()
        
        if not container:
            self.logger.error("Comments container not found")
            return set()

        # More general approach to finding comment articles
        article_selectors = [
            "article.comments-comment-entity",
            "article[data-id]",
            "article[class*='comment']",
            "//article[contains(@class, 'comments-comment')]",
            "//article[@data-id]"
        ]
        
        articles = []
        for selector in article_selectors:
            try:
                if selector.startswith("//"):
                    articles = container.find_elements(By.XPATH, selector)
                else:
                    articles = container.find_elements(By.CSS_SELECTOR, selector)
                
                if articles:
                    self.logger.info(f"Found {len(articles)} comments using selector: {selector}")
                    break
            except Exception:
                continue
        
        if not articles:
            self.logger.error("No comment articles found")
            return set()

        # Collecting author's comment IDs
        for article in articles:
            try:
                # More general approach to finding the author section
                actor_selectors = [
                    ".comments-comment-meta__actor",
                    "div[class*='comment-meta__actor']",
                    "div[class*='actor']",
                    "//div[contains(@class, 'actor')]",
                    "//a[contains(@class, 'actor')]"
                ]
                
                actor_section = None
                for selector in actor_selectors:
                    try:
                        if selector.startswith("//"):
                            actor_section = article.find_element(By.XPATH, selector)
                        else:
                            actor_section = article.find_element(By.CSS_SELECTOR, selector)
                        
                        if actor_section:
                            break
                    except Exception:
                        continue
                
                # Check if this is our author's comment
                if actor_section and Config.AUTOR in actor_section.text:
                    # Find data-id using different methods
                    data_id = article.get_attribute("data-id")
                    
                    if not data_id:
                        # Try finding ID using other attributes
                        for attr in ["id", "article-id", "comment-id"]:
                            data_id = article.get_attribute(attr)
                            if data_id:
                                break
                        
                        # If still no ID, try to find it in classes
                        if not data_id:
                            class_name = article.get_attribute("class")
                            if class_name:
                                # Search for ID pattern in classes
                                id_pattern = re.search(r'id-([a-zA-Z0-9_-]+)', class_name)
                                if id_pattern:
                                    data_id = id_pattern.group(1)
                    
                    if data_id:
                        comment_ids.add(data_id)
                        self.logger.debug(f"Found author's comment: {data_id}")
                        
            except StaleElementReferenceException:
                self.logger.debug("Element became stale during processing")
            except Exception as e:
                self.logger.warning(f"gather_damian_comment_ids: Failed to read article ID: {e}")

        return comment_ids

    def find_article_by_id(self, comment_id: str):
        """Finds an article based on comment ID - with multiple method handling"""
        try:
            # Scroll to top of page
            self.driver.execute_script("window.scrollTo(0, 0)")
            Utils.random_delay(0.5, 1.5)
            
            # Try different selectors
            selectors = [
                f"article.comments-comment-entity[data-id='{comment_id}']",
                f"article[data-id='{comment_id}']",
                f"//article[@data-id='{comment_id}']",
                f"//article[contains(@class, 'comment')][contains(@data-id, '{comment_id}')]",
                f"//article[contains(@class, 'comment')][@id='{comment_id}']"
            ]
            
            for selector in selectors:
                try:
                    if selector.startswith("//"):
                        article = self.driver.find_element(By.XPATH, selector)
                    else:
                        article = self.driver.find_element(By.CSS_SELECTOR, selector)
                    
                    if article:
                        return article
                except Exception:
                    continue
            
            return None
            
        except Exception as e:
            self.logger.warning(f"find_article_by_id({comment_id}): {e}")
            return None

    def find_options_button(self, article):
        """Finds the '...' options button in the comment article"""
        options_selectors = [
            ".artdeco-dropdown__trigger",
            "button.artdeco-dropdown__trigger",
            "button[class*='dropdown__trigger']",
            "//button[contains(@class, 'dropdown__trigger')]",
            "//button[contains(@class, 'overflow') or contains(@class, 'options')]",
            "//button[contains(@aria-label, 'More actions')]"
        ]
        
        for selector in options_selectors:
            try:
                if selector.startswith("//"):
                    options_button = article.find_element(By.XPATH, selector)
                else:
                    options_button = article.find_element(By.CSS_SELECTOR, selector)
                
                if options_button:
                    return options_button
            except Exception:
                continue
        
        return None

    def find_delete_button(self):
        """Finds the 'Delete' button in the comment options menu"""
        delete_selectors = [
            "//span[text()='Usuń']",
            "//span[text()='Delete']",
            "//span[contains(text(), 'Usuń')]",
            "//button[contains(text(), 'Usuń')]",
            "//div[contains(@class, 'dropdown__item')]//span[contains(text(), 'Usuń')]"
        ]
        
        for selector in delete_selectors:
            try:
                delete_buttons = self.driver.find_elements(By.XPATH, selector)
                if delete_buttons:
                    return delete_buttons[0]
            except Exception:
                continue
        
        return None

    def find_confirm_delete_button(self):
        """Finds the delete confirmation button"""
        confirm_selectors = [
            "//button//span[text()='Usuń']",
            "//button//span[text()='Delete']",
            "//button[contains(text(), 'Usuń')]",
            "//button[contains(@class, 'confirm-delete')]",
            "//div[contains(@class, 'confirmation')]//button[contains(text(), 'Usuń')]"
        ]
        
        for selector in confirm_selectors:
            try:
                confirm_button = Utils.wait_and_find_element(self.driver, By.XPATH, selector, timeout=5)
                if confirm_button:
                    return confirm_button
            except Exception:
                continue
        
        return None

    def delete_comment_by_id(self, comment_id: str) -> bool:
        article = self.find_article_by_id(comment_id)
        if not article:
            self.logger.warning(f"Article with ID not found: {comment_id}")
            return False

        try:
            # Scroll to article
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", article)
            Utils.random_delay(0.5, 1.5)

            # Find options button ("...")
            options_button = self.find_options_button(article)
            if not options_button:
                self.logger.warning(f"Options button not found for comment {comment_id}")
                return False
                
            # Click options button
            self.driver.execute_script("arguments[0].click();", options_button)
            Utils.random_delay(0.5, 1.5)

            # Find "Delete" button
            delete_button = self.find_delete_button()
            if not delete_button:
                self.logger.warning(f"No 'Delete' button for comment {comment_id}")
                return False
                
            # Click "Delete" button
            self.driver.execute_script("arguments[0].click();", delete_button)
            Utils.random_delay(0.5, 1.5)

            # Find confirmation button
            confirm_btn = self.find_confirm_delete_button()
            if not confirm_btn:
                self.logger.warning(f"Confirmation button not found for comment {comment_id}")
                return False

            # Click confirmation button
            self.driver.execute_script("arguments[0].click();", confirm_btn)
            Utils.random_delay(1.5, 2.5)
            return True

        except Exception as e:
            self.logger.error(f"Error deleting comment {comment_id}: {e}")
            return False

    def delete_comments_with_retry(self, comment_ids: Set[str]):
        to_remove = set(comment_ids)
        max_passes = 3

        for pass_index in range(1, max_passes+1):
            if not to_remove:
                self.logger.info("No more comments to delete. Finished!")
                break

            self.logger.info(f"Deleting comments (pass {pass_index}/{max_passes}). Remaining: {len(to_remove)}")

            failed_this_round = set()

            for cid in list(to_remove):
                success = self.delete_comment_by_id(cid)
                if success:
                    self.logger.info(f"Comment {cid} deleted")
                    to_remove.remove(cid)
                else:
                    # Failed to delete, will try in next pass
                    failed_this_round.add(cid)

            if len(failed_this_round) == len(to_remove):
                self.logger.info("Refreshing page because no additional comments were deleted")
                self.driver.refresh()
                Utils.random_delay(3, 5)
            else:
                # Refresh and reload to "revive" the DOM
                self.driver.refresh()
                Utils.random_delay(3, 5)

                # After refreshing, go to COMMENTS_URL again
                self.driver.get(Config.COMMENTS_URL)
                Utils.random_delay(3, 5)
                self.load_all_pages()

        if to_remove:
            self.logger.warning("Failed to delete the following comments:")
            for c in to_remove:
                self.logger.warning(f"   - {c}")
        else:
            self.logger.info("All comments have been deleted")

    def find_and_delete_comments(self):
        self.driver.get(Config.COMMENTS_URL)
        Utils.random_delay(2, 4)

        comment_ids = self.gather_damian_comment_ids()
        if not comment_ids:
            self.logger.info("No Damian's comments found to delete")
            return

        self.logger.info(f"Collected {len(comment_ids)} of Damian's comments to delete")
        self.delete_comments_with_retry(comment_ids)
        