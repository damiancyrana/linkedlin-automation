import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager


PROFILE_URL = ""
COMMENTS_URL = f"{PROFILE_URL}/recent-activity/comments/"

EMAIL = ""
PASSWORD = ""


class DriverFactory:
    @staticmethod
    def create_chrome_driver():
        options = Options()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        # Remove the webdriver flag
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver


def wait_and_find_element(driver, by, value, timeout=15):
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
        return element
    except Exception as e:
        print(f"Error finding element {value}: {str(e)}")
        return None


class LinkedInLoginHandler:
    def __init__(self, driver):
        self.driver = driver

    def handle_auth_wall(self):
        login_button = wait_and_find_element(
            self.driver,
            By.CSS_SELECTOR,
            "button.authwall-join-form__form-toggle--bottom"
        )
        if login_button:
            self.driver.execute_script("arguments[0].click();", login_button)
            print("Clicked 'Log in' on the auth wall")
            time.sleep(3)
            return True
        print("Auth wall login button not found")
        return False

    def handle_challenge(self):
        print("Challenge page detected! Waiting for user to solve...")
        while "challenge" in self.driver.current_url:
            print("Waiting for user to solve challenge...")
            time.sleep(5)
        print("Challenge solved. Resuming login")

    def login(self, email, password):
        if "join" in self.driver.current_url or "authwall" in self.driver.page_source:
            if not self.handle_auth_wall():
                return False

        email_input = wait_and_find_element(self.driver, By.CSS_SELECTOR, 'input[name="session_key"]')
        if email_input:
            self.driver.execute_script("arguments[0].value = arguments[1]", email_input, email)
        else:
            return False

        password_input = wait_and_find_element(self.driver, By.CSS_SELECTOR, 'input[name="session_password"]')
        if password_input:
            self.driver.execute_script("arguments[0].value = arguments[1]", password_input, password)
        else:
            return False

        submit_button = wait_and_find_element(self.driver, By.CSS_SELECTOR, 'button[data-id="sign-in-form__submit-btn"]')
        if submit_button:
            self.driver.execute_script("arguments[0].click();", submit_button)
        else:
            return False

        time.sleep(5)

        if "challenge" in self.driver.current_url:
            self.handle_challenge()

        if COMMENTS_URL not in self.driver.current_url:
            self.driver.get(COMMENTS_URL)
            time.sleep(3)

        return COMMENTS_URL in self.driver.current_url


class LinkedInCommentHandler:
    def __init__(self, driver):
        self.driver = driver

    def delete_comment(self, comment, index):
        try:
            options_button = comment.find_element(By.CSS_SELECTOR, ".artdeco-dropdown__trigger")
            self.driver.execute_script("arguments[0].click();", options_button)
            time.sleep(1)

            delete_button = self.driver.find_elements(By.XPATH, "//span[text()='Usuń']")
            if delete_button:
                self.driver.execute_script("arguments[0].click();", delete_button[0])
                time.sleep(1)

                confirm_delete_button = wait_and_find_element(self.driver, By.XPATH, "//button//span[text()='Usuń']")
                if confirm_delete_button:
                    self.driver.execute_script("arguments[0].click();", confirm_delete_button)
                    time.sleep(2)
                    print(f"Comment #{index} deleted")
                else:
                    print(f"Confirmation delete button not found for comment #{index}")
            else:
                print(f"Delete option not available for comment #{index}. Skipping...")
        except StaleElementReferenceException:
            print(f"Stale element detected for comment #{index}. Skipping...")
        except Exception as e:
            print(f"Error deleting comment #{index}: {e}")

    def find_and_delete_comments(self):
        self.driver.get(COMMENTS_URL)
        time.sleep(3)

        while True:
            comments_container = wait_and_find_element(self.driver, By.CLASS_NAME, "scaffold-finite-scroll__content")
            if not comments_container:
                print("Comments container not found")
                return

            comment_containers = comments_container.find_elements(By.CLASS_NAME, "comments-comment-meta__container--parent")
            print(f"Found {len(comment_containers)} comments.")

            for index, comment in enumerate(comment_containers, start=1):
                self.delete_comment(comment, index)

            load_more_button = wait_and_find_element(self.driver, By.CSS_SELECTOR, ".scaffold-finite-scroll__load-button")
            if load_more_button:
                self.driver.execute_script("arguments[0].click();", load_more_button)
                time.sleep(3)
            else:
                print("No more comments to load")
                break


def main():
    driver = None
    try:
        driver = DriverFactory.create_chrome_driver()
        driver.get(PROFILE_URL)

        login_handler = LinkedInLoginHandler(driver)
        if login_handler.login(EMAIL, PASSWORD):
            print("Successfully logged in.")
            comment_handler = LinkedInCommentHandler(driver)
            comment_handler.find_and_delete_comments()
        else:
            print("Login failed")

        input("Press Enter to close the browser...")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    main()
