import time
from typing import List, Set
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException,
    NoSuchElementException,
)
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options


AUTOR = ""   # Imię i nazwisko autora komentarza
PROFILE_URL = ""  # URL profilu LinkedIn (WAZNE!!! bez końcowego /)
COMMENTS_URL = f"{PROFILE_URL}/recent-activity/comments/"

EMAIL = ""
PASSWORD = ""


def wait_and_find_element(driver, by, value, timeout=15):
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
    except Exception as e:
        print(f"[ERROR] Nie znaleziono elementu {value} w czasie {timeout}s: {str(e)}")
        return None


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
        # ukrycie flagi webdriver w JS
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver


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
            time.sleep(3)
            return True
        return False

    def handle_challenge(self):
        print("[INFO] Oczekiwanie na rozwiązanie ewentualnego challenge'a / captcha...")
        while "challenge" in self.driver.current_url:
            time.sleep(5)
        print("[INFO] Challenge rozwiązany!")

    def login(self, email, password):
        # Auth wall?
        if "join" in self.driver.current_url or "authwall" in self.driver.page_source:
            self.handle_auth_wall()

        # Wpisanie e-maila
        email_input = wait_and_find_element(
            self.driver, By.CSS_SELECTOR, 'input[name="session_key"]'
        )
        if email_input:
            self.driver.execute_script("arguments[0].value = arguments[1]", email_input, email)
        else:
            print("[ERROR] Nie udało się znaleźć pola e-mail!")
            return False

        # Wpisanie hasła
        password_input = wait_and_find_element(
            self.driver, By.CSS_SELECTOR, 'input[name="session_password"]'
        )
        if password_input:
            self.driver.execute_script("arguments[0].value = arguments[1]", password_input, password)
        else:
            print("[ERROR] Nie udało się znaleźć pola password!")
            return False

        # Kliknięcie 'Zaloguj'
        submit_button = wait_and_find_element(
            self.driver, By.CSS_SELECTOR, 'button[data-id="sign-in-form__submit-btn"]'
        )
        if submit_button:
            self.driver.execute_script("arguments[0].click();", submit_button)
            time.sleep(5)
            if "challenge" in self.driver.current_url:
                self.handle_challenge()
        else:
            print("[ERROR] Nie udało się znaleźć przycisku 'Zaloguj'.")
            return False

        if COMMENTS_URL not in self.driver.current_url:
            self.driver.get(COMMENTS_URL)
            time.sleep(3)

        return COMMENTS_URL in self.driver.current_url


class LinkedInCommentHandler:
    def __init__(self, driver):
        self.driver = driver

    def expand_replies(self):
        # Zobacz więcej odpowiedzi
        more_replies_buttons = self.driver.find_elements(
            By.XPATH, "//button[contains(text(), 'Zobacz więcej odpowiedzi')]"
        )
        for btn in more_replies_buttons:
            try:
                self.driver.execute_script("arguments[0].click();", btn)
                time.sleep(1.5)
            except Exception:
                pass

        # Zobacz poprzednie odpowiedzi
        prev_replies_buttons = self.driver.find_elements(
            By.XPATH, "//button[contains(text(), 'Zobacz poprzednie odpowiedzi')]"
        )
        for btn in prev_replies_buttons:
            try:
                self.driver.execute_script("arguments[0].click();", btn)
                time.sleep(2)
            except Exception:
                pass

    def load_all_pages(self):
        while True:
            self.expand_replies()
            load_more_button = self.driver.find_elements(
                By.CSS_SELECTOR, ".scaffold-finite-scroll__load-button"
            )
            if load_more_button:
                try:
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView(true);", load_more_button[0]
                    )
                    time.sleep(0.5)
                    self.driver.execute_script("arguments[0].click();", load_more_button[0])
                    time.sleep(2)
                except Exception:
                    print("[WARN] Nie udało się kliknąć 'Pokaż więcej wyników'")
                    break
            else:
                break

    def gather_damian_comment_ids(self) -> Set[str]:
        comment_ids = set()
        self.load_all_pages()

        container = wait_and_find_element(
            self.driver, By.CLASS_NAME, "scaffold-finite-scroll__content", timeout=10
        )
        if not container:
            print("[ERROR] Nie znaleziono kontenera komentarzy")
            return set()

        # Szukamy wszystkich <article> z komentarzem
        articles = container.find_elements(By.CSS_SELECTOR, "article.comments-comment-entity")
        print(f"[INFO] Znaleziono {len(articles)} komentarzy (article.comments-comment-entity)")

        for article in articles:
            try:
                actor_section = article.find_element(By.CSS_SELECTOR, ".comments-comment-meta__actor")
                if AUTOR in actor_section.text:
                    data_id = article.get_attribute("data-id")
                    if data_id:
                        comment_ids.add(data_id)
            except StaleElementReferenceException:
                pass
            except Exception as e:
                print(f"[WARN] gather_damian_comment_ids: Nie udało się odczytać ID artykułu: {e}")

        return comment_ids

    def find_article_by_id(self, comment_id: str):
        try:
            self.driver.execute_script("window.scrollTo(0, 0)")
            time.sleep(1)
            selector = f"article.comments-comment-entity[data-id='{comment_id}']"
            return self.driver.find_element(By.CSS_SELECTOR, selector)
        except NoSuchElementException:
            return None
        except StaleElementReferenceException:
            return None
        except Exception as e:
            print(f"[WARN] find_article_by_id({comment_id}): {e}")
            return None

    def delete_comment_by_id(self, comment_id: str) -> bool:
        article = self.find_article_by_id(comment_id)
        if not article:
            return False

        try:
            self.driver.execute_script("arguments[0].scrollIntoView(true);", article)
            time.sleep(1)

            # Kliknij w "..."
            options_button = article.find_element(By.CSS_SELECTOR, ".artdeco-dropdown__trigger")
            self.driver.execute_script("arguments[0].click();", options_button)
            time.sleep(1)

            # Przycisk "Usuń"
            delete_buttons = self.driver.find_elements(By.XPATH, "//span[text()='Usuń']")
            if not delete_buttons:
                print(f"[WARN] Brak przycisku 'Usuń' dla komentarza {comment_id}")
                return False
            self.driver.execute_script("arguments[0].click();", delete_buttons[0])
            time.sleep(1)

            # Potwierdzenie
            confirm_btn = wait_and_find_element(
                self.driver, By.XPATH, "//button//span[text()='Usuń']", timeout=5
            )

            if not confirm_btn:
                return False

            self.driver.execute_script("arguments[0].click();", confirm_btn)
            time.sleep(2)
            return True

        except Exception as e:
            print(f"[ERROR] Błąd usuwania komentarza {comment_id}: {e}")
            return False

    def delete_comments_with_retry(self, comment_ids: Set[str]):
        to_remove = set(comment_ids)
        max_passes = 3

        for pass_index in range(1, max_passes+1):
            if not to_remove:
                print("[INFO] Nie ma już komentarzy do usunięcia. Koniec!")
                break

            print(f"[INFO] Usuwanie komentarzy (pass {pass_index}/{max_passes}). Zostało: {len(to_remove)}")

            failed_this_round = set()

            for cid in list(to_remove):
                success = self.delete_comment_by_id(cid)
                if success:
                    print(f"[INFO] Komentarz {cid} usunięty")
                    to_remove.remove(cid)
                else:
                    # Nie udało się usunąć, spróbujemy w następnym "passie"
                    failed_this_round.add(cid)

            if len(failed_this_round) == len(to_remove):
                print("[INFO] Odświeżam stronę, bo nie udało się usunąć dodatkowych komentarzy")
                self.driver.refresh()
                time.sleep(5)
            else:
                # Odśwież i wczytaj ponownie, by "ożywić" DOM
                self.driver.refresh()
                time.sleep(5)

                # Po odświeżeniu wchodzimy jeszcze raz w COMMENTS_URL
                self.driver.get(COMMENTS_URL)
                time.sleep(5)
                self.load_all_pages()

        if to_remove:
            print("[WARN] Nie udało się ostatecznie usunąć następujących komentarzy:")
            for c in to_remove:
                print(f"   - {c}")
        else:
            print("[INFO] Wszystkie komentarze zostały usunięte")

    def find_and_delete_comments(self):
        self.driver.get(COMMENTS_URL)
        time.sleep(3)

        comment_ids = self.gather_damian_comment_ids()
        if not comment_ids:
            print("[INFO] Nie znaleziono komentarzy Damiana do usunięcia")
            return

        print(f"[INFO] Zebrano {len(comment_ids)} komentarzy Damiana do usunięcia")
        self.delete_comments_with_retry(comment_ids)


def main():
    driver = None
    try:
        driver = DriverFactory.create_chrome_driver()
        driver.get(PROFILE_URL)

        login_handler = LinkedInLoginHandler(driver)
        if login_handler.login(EMAIL, PASSWORD):
            print("[INFO] Zalogowano pomyślnie.")
            comment_handler = LinkedInCommentHandler(driver)
            comment_handler.find_and_delete_comments()
        else:
            print("[ERROR] Logowanie nie powiodło się")

        input("Naciśnij Enter, aby zamknąć przeglądarkę...")
    except Exception as e:
        print(f"[FATAL] Wystąpił nieoczekiwany błąd: {e}")
    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    main()
