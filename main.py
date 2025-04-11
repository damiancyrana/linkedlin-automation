import time
import csv
import random
import os
import re
import json
import threading
import queue
from typing import List, Set, Dict
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




def random_delay(min_seconds=1, max_seconds=3):
    """Dodaje losowe opóźnienie, aby symulować ludzkiego użytkownika"""
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)


def wait_and_find_element(driver, by, value, timeout=15):
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
    except Exception as e:
        print(f"[ERROR] Nie znaleziono elementu {value} w czasie {timeout}s: {str(e)}")
        return None


def create_filename_from_query(query):
    """Tworzy nazwę pliku CSV na podstawie zapytania wyszukiwania"""
    # Zamień spacje na podkreślniki i usuń znaki niedozwolone w nazwach plików
    clean_query = re.sub(r'[^\w\s-]', '', query.lower()).strip().replace(' ', '_')
    return f"{clean_query}_linkedin_profiles.csv"


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
            random_delay(2, 4)
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
            random_delay(4, 6)
            if "challenge" in self.driver.current_url:
                self.handle_challenge()
        else:
            print("[ERROR] Nie udało się znaleźć przycisku 'Zaloguj'.")
            return False

        # Weryfikacja zalogowania - bardziej ogólna, działa dla wszystkich przypadków
        random_delay(2, 4)
        return any(marker in self.driver.current_url for marker in ["/feed", "/in/", "mynetwork"])


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
                random_delay(1, 2)
            except Exception:
                pass

        # Zobacz poprzednie odpowiedzi
        prev_replies_buttons = self.driver.find_elements(
            By.XPATH, "//button[contains(text(), 'Zobacz poprzednie odpowiedzi')]"
        )
        for btn in prev_replies_buttons:
            try:
                self.driver.execute_script("arguments[0].click();", btn)
                random_delay(1.5, 2.5)
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
                    random_delay(0.5, 1)
                    self.driver.execute_script("arguments[0].click();", load_more_button[0])
                    random_delay(1.5, 2.5)
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
            random_delay(0.5, 1.5)
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
            random_delay(0.5, 1.5)

            # Kliknij w "..."
            options_button = article.find_element(By.CSS_SELECTOR, ".artdeco-dropdown__trigger")
            self.driver.execute_script("arguments[0].click();", options_button)
            random_delay(0.5, 1.5)

            # Przycisk "Usuń"
            delete_buttons = self.driver.find_elements(By.XPATH, "//span[text()='Usuń']")
            if not delete_buttons:
                print(f"[WARN] Brak przycisku 'Usuń' dla komentarza {comment_id}")
                return False
            self.driver.execute_script("arguments[0].click();", delete_buttons[0])
            random_delay(0.5, 1.5)

            # Potwierdzenie
            confirm_btn = wait_and_find_element(
                self.driver, By.XPATH, "//button//span[text()='Usuń']", timeout=5
            )

            if not confirm_btn:
                return False

            self.driver.execute_script("arguments[0].click();", confirm_btn)
            random_delay(1.5, 2.5)
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
                random_delay(3, 5)
            else:
                # Odśwież i wczytaj ponownie, by "ożywić" DOM
                self.driver.refresh()
                random_delay(3, 5)

                # Po odświeżeniu wchodzimy jeszcze raz w COMMENTS_URL
                self.driver.get(COMMENTS_URL)
                random_delay(3, 5)
                self.load_all_pages()

        if to_remove:
            print("[WARN] Nie udało się ostatecznie usunąć następujących komentarzy:")
            for c in to_remove:
                print(f"   - {c}")
        else:
            print("[INFO] Wszystkie komentarze zostały usunięte")

    def find_and_delete_comments(self):
        self.driver.get(COMMENTS_URL)
        random_delay(2, 4)

        comment_ids = self.gather_damian_comment_ids()
        if not comment_ids:
            print("[INFO] Nie znaleziono komentarzy Damiana do usunięcia")
            return

        print(f"[INFO] Zebrano {len(comment_ids)} komentarzy Damiana do usunięcia")
        self.delete_comments_with_retry(comment_ids)


class LinkedInPeopleSearchHandler:
    def __init__(self, driver, search_query):
        self.driver = driver
        self.profiles = []
        self.search_query = search_query
        self.csv_filename = create_filename_from_query(search_query)
        self.csv_initialized = False
        self.field_names = ["name", "title", "location", "current_company", "profile_url"]

    def try_multiple_selectors(self, element, selectors, method=By.CSS_SELECTOR):
        """Próbuje wielu selektorów, zwraca pierwszy znaleziony element"""
        for selector in selectors:
            try:
                found = element.find_element(method, selector)
                if found:
                    return found
            except Exception:
                continue
        return None
        
    def search_people(self, search_query):
        """Wykonuje wyszukiwanie osób na LinkedIn"""
        print(f"[INFO] Wyszukiwanie osób dla zapytania: '{search_query}'")
        
        # Przejdź do strony głównej LinkedIn
        self.driver.get("https://www.linkedin.com/")
        random_delay(2, 4)
        
        # Znajdź pole wyszukiwania
        search_input = wait_and_find_element(
            self.driver, 
            By.CSS_SELECTOR, 
            "input.search-global-typeahead__input"
        )
        
        if not search_input:
            print("[ERROR] Nie znaleziono pola wyszukiwania")
            return False
        
        # Wyczyść pole i wpisz zapytanie
        search_input.clear()
        search_input.send_keys(search_query)
        random_delay(0.5, 1.5)
        search_input.send_keys(Keys.ENTER)
        random_delay(2, 4)
        
        # Sprawdź, czy jesteśmy na stronie wyników wyszukiwania
        try:
            # Przejdź do wyników wyszukiwania osób (jeśli nie jesteśmy tam jeszcze)
            people_results_selectors = [
                "//a[contains(text(), 'Zobacz wszystkie wyniki osób')]",
                "//a[contains(text(), 'See all people results')]",
                "//a[contains(@href, '/search/results/people')]"
            ]
            
            for selector in people_results_selectors:
                try:
                    people_link = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    self.driver.execute_script("arguments[0].click();", people_link)
                    random_delay(2, 4)
                    break
                except TimeoutException:
                    continue
        except TimeoutException:
            # Możliwe, że już jesteśmy na stronie wyników wyszukiwania osób
            pass
        
        return "search/results/people" in self.driver.current_url

    def extract_profile_data(self, profile_element):
        """Ekstrahuje dane profilu z elementu li z odpornością na zmiany klas CSS"""
        profile_data = {
            "name": "",
            "title": "",
            "location": "",
            "current_company": "",
            "profile_url": ""
        }
        
        try:
            # 1. Znajdowanie imienia i nazwiska - bardziej niezawodne selektory
            name_selectors = [
                "span.oKYGlVrMBpBFJGUyCKYRrybaptZoazvfkw a", 
                "span[class*='t-16'] a", 
                ".entity-result__title-text a",
                "a[href*='/in/']"
            ]
            
            name_element = self.try_multiple_selectors(profile_element, name_selectors)
            
            if not name_element:
                # Próba z XPath
                try:
                    name_element = profile_element.find_element(By.XPATH, ".//a[contains(@href, '/in/')]")
                except:
                    pass
            
            if name_element:
                profile_data["name"] = name_element.text.strip()
                profile_data["profile_url"] = name_element.get_attribute("href").split("?")[0]
            
            # 2. Pobieranie tytułu stanowiska - wiele metod
            title_selectors = [
                "div.ouqFDUJCzhugPNpegQHNhfazHmnfHzSY",
                "div[class*='t-black'][class*='t-normal']",
                ".entity-result__primary-subtitle"
            ]
            
            title_element = self.try_multiple_selectors(profile_element, title_selectors)
            if title_element:
                profile_data["title"] = title_element.text.strip()
            
            # 3. Pobieranie lokalizacji - na podstawie pozycji lub tekstu
            location_selectors = [
                "div.yrFkFoofyxGfbvnrSMDkNyhQrcHfzJoYxXKs",
                "div[class*='t-normal']:not([class*='t-black'])",
                ".entity-result__secondary-subtitle"
            ]
            
            location_element = self.try_multiple_selectors(profile_element, location_selectors)
            if location_element:
                profile_data["location"] = location_element.text.strip()
            
            # 4. Pobieranie informacji o obecnej firmie
            summary_selectors = [
                "p.vTpTcUIchIiDnwMRhFHzqVOINVNBpiWDnpYA",
                "p[class*='entity-result__summary']", 
                "p[class*='t-12']"
            ]
            
            summary_element = self.try_multiple_selectors(profile_element, summary_selectors)
            if summary_element:
                summary_text = summary_element.text.strip()
                if "Obecnie:" in summary_text:
                    current_company = summary_text.split("Obecnie:")[1].strip()
                    profile_data["current_company"] = current_company
                
        except Exception as e:
            print(f"[WARN] Błąd podczas ekstrahowania danych profilu: {e}")
            
        return profile_data
    
    def init_csv_file(self):
        """Inicjalizuje plik CSV z nagłówkami"""
        if not self.csv_initialized:
            file_exists = os.path.isfile(self.csv_filename)
            
            with open(self.csv_filename, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=self.field_names)
                if not file_exists:
                    writer.writeheader()
            
            self.csv_initialized = True
            print(f"[INFO] Zainicjalizowano plik CSV: {self.csv_filename}")

    def append_profile_to_csv(self, profile):
        """Dodaje pojedynczy profil do pliku CSV"""
        try:
            with open(self.csv_filename, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=self.field_names)
                writer.writerow(profile)
            print(f"[INFO] Dodano do CSV: {profile['name']} - {profile['title']}")
        except Exception as e:
            print(f"[ERROR] Błąd podczas zapisywania do CSV: {e}")
        
    def process_search_results_page(self):
        """Przetwarza stronę wyników wyszukiwania i pobiera dane profilów"""
        print("[INFO] Przetwarzanie strony wyników wyszukiwania")
        
        # Poczekaj na załadowanie wyników
        wait_and_find_element(
            self.driver, 
            By.CSS_SELECTOR, 
            "ul[class*='list-style-none']"
        )
        
        random_delay(2, 3)
        
        # Inicjalizacja pliku CSV jeśli jeszcze nie istnieje
        if not self.csv_initialized:
            self.init_csv_file()
        
        # Znajdź wszystkie elementy profili na stronie - używamy wielu selektorów
        profile_selectors = [
            "li.GRAOxLqrJyBKXYoRPUQntEwHpJjCqc",
            "li.reusable-search__result-container",
            "li.search-result"
        ]
        
        profiles_found = []
        profile_elements = []
        
        for selector in profile_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    profile_elements = elements
                    break
            except:
                continue
        
        for profile_element in profile_elements:
            try:
                # Sprawdź, czy element to faktycznie profil osoby (a nie reklama lub inny element)
                if "Reaktywuj Premium" in profile_element.text or "Premium" in profile_element.text:
                    continue
                    
                # Ekstrahuj dane profilu
                profile_data = self.extract_profile_data(profile_element)
                
                # Dodaj tylko jeśli udało się pobrać przynajmniej imię i nazwisko
                if profile_data["name"]:  
                    profiles_found.append(profile_data)
                    # Natychmiast zapisz do CSV
                    self.append_profile_to_csv(profile_data)
                    print(f"[INFO] Znaleziono profil: {profile_data['name']} - {profile_data['title']}")
            except StaleElementReferenceException:
                print("[WARN] Element stracił ważność, pomijam")
                continue
            except Exception as e:
                print(f"[WARN] Błąd podczas przetwarzania profilu: {e}")
                
        return profiles_found

    def navigate_to_next_page(self):
        """Nawiguje do następnej strony wyników, jeśli jest dostępna."""
        try:
            # Najpierw poczekaj na załadowanie paginacji
            pagination = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "artdeco-pagination"))
            )
            
            # Scrolluj do paginacji
            self.driver.execute_script("arguments[0].scrollIntoView(true);", pagination)
            random_delay(1, 2)
            
            # Znajdź przycisk "Dalej" - kilka metod
            try:
                # Metoda 1: Po tekście "Dalej"
                next_button = self.driver.find_element(By.XPATH, 
                    "//button[contains(@class, 'artdeco-pagination__button--next')]")
                
                # Sprawdź czy przycisk nie jest wyłączony
                if "artdeco-button--disabled" in next_button.get_attribute("class"):
                    print("[INFO] Przycisk 'Dalej' jest wyłączony - osiągnięto ostatnią stronę")
                    return False
                    
                print("[INFO] Przechodzenie do następnej strony...")
                # Najpierw scrolluj do przycisku
                self.driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                random_delay(1, 2)
                
                # Kliknij za pomocą JavaScriptu (bardziej niezawodne)
                self.driver.execute_script("arguments[0].click();", next_button)
                
                # Czekaj na odświeżenie strony
                WebDriverWait(self.driver, 10).until(
                    EC.staleness_of(pagination)
                )
                
                # Czekaj na ponowne załadowanie wyników
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "ul[class*='list-style-none']"))
                )
                
                random_delay(3, 5)
                return True
                
            except NoSuchElementException:
                print("[INFO] Nie znaleziono przycisku 'Dalej' - osiągnięto ostatnią stronę")
                return False
                
        except Exception as e:
            print(f"[ERROR] Problem z przejściem do następnej strony: {str(e)}")
            # Dodaj ponowną próbę z inną metodą
            try:
                # Spróbuj innego selektora
                next_button = self.driver.find_element(By.CSS_SELECTOR, 
                    "button.artdeco-pagination__button--next")
                self.driver.execute_script("arguments[0].click();", next_button)
                random_delay(3, 5)
                return True
            except:
                return False

    def get_total_pages(self):
        """Próbuje odczytać całkowitą liczbę stron wyników"""
        try:
            pagination_text = self.driver.find_element(
                By.CSS_SELECTOR, 
                "div.artdeco-pagination__page-state"
            ).text
            
            # Format tekstu: "Strona X z Y"
            parts = pagination_text.split(" ")
            if len(parts) >= 4:
                return int(parts[3])
            return 100  # Domyślnie załóż dużą liczbę stron
        except Exception:
            return 100  # Wartość domyślna, jeśli nie można odczytać
            
    def search_and_collect_profiles(self):
        """Wyszukuje profile i zbiera dane z wszystkich dostępnych stron"""
        if not self.search_people(self.search_query):
            print("[ERROR] Nie udało się wyszukać osób")
            return []
            
        all_profiles = []
        current_page = 1
        total_pages = self.get_total_pages()
        
        print(f"[INFO] Znaleziono łącznie {total_pages} stron wyników")
        
        while True:
            print(f"[INFO] Przetwarzanie strony {current_page} z {total_pages}")
            
            # Pobierz profile z bieżącej strony
            page_profiles = self.process_search_results_page()
            all_profiles.extend(page_profiles)
            
            print(f"[INFO] Znaleziono {len(page_profiles)} profili na stronie {current_page}")
            
            # Przejdź do następnej strony
            if not self.navigate_to_next_page():
                break
                
            current_page += 1
            
            # Dodaj losowe opóźnienie między stronami
            random_delay(3, 7)
                
        print(f"[INFO] Zebrano dane {len(all_profiles)} profili z {current_page} stron")
        print(f"[INFO] Wszystkie dane zostały zapisane do pliku {self.csv_filename}")
        return all_profiles


class LinkedInProfileParser:
    def __init__(self, driver):
        self.driver = driver
        
    def get_text_safely(self, element, selector, method=By.CSS_SELECTOR):
        """Bezpieczne pobieranie tekstu z elementu"""
        try:
            found = element.find_element(method, selector)
            if found:
                return found.text.strip()
        except:
            pass
        return ""
        
    def try_multiple_selectors(self, element, selectors, method=By.CSS_SELECTOR):
        """Próbuje wielu selektorów, zwraca pierwszy znaleziony element"""
        for selector in selectors:
            try:
                found = element.find_element(method, selector)
                if found:
                    return found
            except:
                continue
        return None
        
    def scroll_to_element(self, element):
        """Przewija do elementu, aby załadować dynamiczną zawartość"""
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            random_delay(1, 2)
        except:
            pass
            
    def expand_section(self, section_name):
        """Rozwija sekcję, jeśli jest zwinięta"""
        try:
            # Szukaj przycisku "Pokaż więcej" w sekcji
            show_more_buttons = self.driver.find_elements(
                By.XPATH, 
                f"//section[contains(@id, '{section_name}')]//button[contains(text(), 'Pokaż więcej') or contains(text(), 'See more') or contains(@class, 'inline-show-more-text__button')]"
            )
            
            for btn in show_more_buttons:
                try:
                    self.scroll_to_element(btn)
                    self.driver.execute_script("arguments[0].click();", btn)
                    random_delay(0.5, 1.5)
                except:
                    pass
        except Exception as e:
            print(f"[WARN] Nie udało się rozwinąć sekcji {section_name}: {e}")
            
    def load_full_page(self):
        """Ładuje całą stronę profilu, przewijając do końca"""
        # Przewijaj do dołu w odstępach, aby załadować dynamiczną zawartość
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        
        while True:
            # Przewiń w dół
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            random_delay(1.5, 2.5)
            
            # Poczekaj na załadowanie treści
            random_delay(1, 2)
            
            # Oblicz nową wysokość i sprawdź, czy osiągnięto dół strony
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            
        # Przewiń z powrotem na górę
        self.driver.execute_script("window.scrollTo(0, 0);")
        random_delay(1, 2)
        
    def expand_all_sections(self):
        """Rozszerza wszystkie sekcje profilu"""
        # Lista możliwych sekcji
        sections = ["about", "experience", "education", "skills", "languages", "courses", "projects"]
        
        # Rozwiń każdą sekcję
        for section in sections:
            self.expand_section(section)
            
        # Szukaj wszystkich przycisków "Pokaż więcej" / "See more" na stronie
        show_more_buttons = self.driver.find_elements(
            By.XPATH, 
            "//button[contains(text(), 'Zobacz więcej') or contains(text(), 'See more') or contains(text(), 'Pokaż więcej') or contains(@class, 'inline-show-more-text__button')]"
        )
        
        for btn in show_more_buttons:
            try:
                self.scroll_to_element(btn)
                self.driver.execute_script("arguments[0].click();", btn)
                random_delay(0.5, 1)
            except:
                pass
        
    def extract_basic_info(self):
        """Ekstrahuje podstawowe informacje o profilu"""
        basic_info = {
            "name": "",
            "headline": "",
            "location": "",
            "followers": "",
            "connections": ""
        }
        
        # Imię i nazwisko
        name_selectors = [
            "h1.text-heading-xlarge", 
            "h1.inline", 
            "h1.pv-top-card--list"
        ]
        
        for selector in name_selectors:
            try:
                name_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                if name_element:
                    basic_info["name"] = name_element.text.strip()
                    break
            except:
                pass
                
        # Nagłówek/stanowisko
        headline_selectors = [
            "div.text-body-medium.break-words", 
            ".pv-top-card--list-bullet"
        ]
        
        for selector in headline_selectors:
            try:
                headline_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                if headline_element:
                    basic_info["headline"] = headline_element.text.strip()
                    break
            except:
                pass
                
        # Lokalizacja
        location_selectors = [
            "span.text-body-small.inline", 
            ".pv-top-card--list-bullet"
        ]
        
        for selector in location_selectors:
            try:
                location_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if location_elements and len(location_elements) > 0:
                    # Często lokalizacja jest drugim elementem w tym formacie
                    if len(location_elements) >= 2:
                        basic_info["location"] = location_elements[1].text.strip()
                    else:
                        basic_info["location"] = location_elements[0].text.strip()
                    break
            except:
                pass
                
        # Obserwujący
        try:
            followers_element = self.driver.find_element(
                By.XPATH, 
                "//span[contains(text(), 'obserwujących') or contains(text(), 'followers')]"
            )
            if followers_element:
                followers_text = followers_element.text.strip()
                # Wyodrębnij liczbę z tekstu
                basic_info["followers"] = re.search(r'\d+(?:,\d+)*', followers_text).group(0)
        except:
            pass
            
        # Liczba kontaktów
        try:
            connections_element = self.driver.find_element(
                By.XPATH, 
                "//span[contains(text(), 'kontakt') or contains(text(), 'connection')]"
            )
            if connections_element:
                connections_text = connections_element.text.strip()
                # Wyodrębnij liczbę z tekstu
                matches = re.search(r'(\d+(?:\+|\s*\+)?)', connections_text)
                if matches:
                    basic_info["connections"] = matches.group(1)
        except:
            pass
            
        return basic_info
        
    def extract_about_section(self):
        """Ekstrahuje sekcję 'O mnie'"""
        about_text = ""
        
        # Znajdź sekcję "O mnie"
        about_selectors = [
            "section#about div.display-flex.ph5.pv3", 
            "section[id='about'] .pv-profile-section__section-info",
            "section[id='about'] .inline-show-more-text"
        ]
        
        for selector in about_selectors:
            try:
                about_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                if about_element:
                    self.scroll_to_element(about_element)
                    about_text = about_element.text.strip()
                    break
            except:
                pass
                
        # Jeśli nie udało się znaleźć tekstu, spróbuj innej metody
        if not about_text:
            try:
                about_section = self.driver.find_element(By.ID, "about")
                if about_section:
                    self.scroll_to_element(about_section)
                    # Spróbuj znaleźć paragraf lub div z tekstem
                    text_elements = about_section.find_elements(
                        By.XPATH, 
                        ".//div[contains(@class, 'text') or contains(@class, 'display-flex')]"
                    )
                    
                    for elem in text_elements:
                        text = elem.text.strip()
                        if text and len(text) > 50:  # Zakładamy, że sekcja "O mnie" ma co najmniej 50 znaków
                            about_text = text
                            break
            except:
                pass
                
        return about_text
        
    def extract_experience(self):
        """Ekstrahuje doświadczenie zawodowe"""
        experience_items = []
        
        # Znajdź sekcję doświadczenia
        experience_section = None
        experience_selectors = [
            "section#experience", 
            "section[id='experience']"
        ]
        
        for selector in experience_selectors:
            try:
                experience_section = self.driver.find_element(By.CSS_SELECTOR, selector)
                if experience_section:
                    self.scroll_to_element(experience_section)
                    break
            except:
                pass
                
        if not experience_section:
            return experience_items
        
        # Rozwiń wszystkie przyciski "więcej" w sekcji
        show_more_buttons = experience_section.find_elements(
            By.XPATH, 
            ".//button[contains(text(), 'Pokaż więcej') or contains(text(), 'Zobacz więcej') or contains(text(), 'See more')]"
        )
        
        for btn in show_more_buttons:
            try:
                self.scroll_to_element(btn)
                self.driver.execute_script("arguments[0].click();", btn)
                random_delay(0.5, 1)
            except:
                pass
                
        # Szukaj elementów doświadczenia w różnych formatach
        experience_elements = []
        
        # Wariant 1: Standardowy format
        try:
            elements = experience_section.find_elements(By.CSS_SELECTOR, "li.artdeco-list__item")
            if elements:
                experience_elements = elements
        except:
            pass
            
        # Wariant 2: Alternatywny format
        if not experience_elements:
            try:
                elements = experience_section.find_elements(By.XPATH, ".//div[contains(@class, 'pvs-entity')]")
                if elements:
                    experience_elements = elements
            except:
                pass
                
        # Iteruj przez elementy doświadczenia
        for exp_element in experience_elements:
            try:
                experience_item = {}
                
                # Nazwa firmy
                company_elements = exp_element.find_elements(
                    By.XPATH, 
                    ".//span[contains(@class, 'hoverable-link-text') or contains(@class, 't-bold')]"
                )
                
                if company_elements and len(company_elements) > 0:
                    experience_item["company"] = company_elements[0].text.strip()
                
                # Stanowisko
                title_elements = exp_element.find_elements(
                    By.XPATH, 
                    ".//span[contains(@class, 't-14') and contains(@class, 't-bold')]"
                )
                
                if title_elements and len(title_elements) > 0:
                    # W niektórych formatach tytuł jest w pierwszym elemencie
                    experience_item["title"] = title_elements[0].text.strip()
                    
                # Daty
                date_elements = exp_element.find_elements(
                    By.XPATH, 
                    ".//span[contains(@class, 't-14') and contains(@class, 't-normal') and contains(@class, 't-black--light')]"
                )
                
                if date_elements and len(date_elements) > 0:
                    for date_elem in date_elements:
                        if "20" in date_elem.text or "19" in date_elem.text:  # Prawdopodobnie zawiera rok
                            experience_item["date_range"] = date_elem.text.strip()
                            break
                
                # Lokalizacja
                location_elements = exp_element.find_elements(
                    By.XPATH, 
                    ".//span[contains(@class, 't-14') and contains(@class, 't-normal') and contains(@class, 't-black--light')]"
                )
                
                if location_elements and len(location_elements) > 1:
                    # Zakładamy, że lokalizacja jest w kolejnym elemencie po datach
                    experience_item["location"] = location_elements[1].text.strip()
                
                # Opis
                description_elements = exp_element.find_elements(
                    By.XPATH, 
                    ".//div[contains(@class, 'inline-show-more-text')]"
                )
                
                if description_elements and len(description_elements) > 0:
                    experience_item["description"] = description_elements[0].text.strip()
                
                # Dodaj do listy, jeśli udało się znaleźć co najmniej firmę lub stanowisko
                if "company" in experience_item or "title" in experience_item:
                    experience_items.append(experience_item)
                    
            except Exception as e:
                print(f"[WARN] Błąd podczas ekstrahowania doświadczenia: {e}")
                
        return experience_items
        
    def extract_education(self):
        """Ekstrahuje wykształcenie"""
        education_items = []
        
        # Znajdź sekcję wykształcenia
        education_section = None
        education_selectors = [
            "section#education", 
            "section[id='education']"
        ]
        
        for selector in education_selectors:
            try:
                education_section = self.driver.find_element(By.CSS_SELECTOR, selector)
                if education_section:
                    self.scroll_to_element(education_section)
                    break
            except:
                pass
                
        if not education_section:
            return education_items
            
        # Znajdź wszystkie elementy wykształcenia
        education_elements = []
        
        try:
            elements = education_section.find_elements(By.CSS_SELECTOR, "li.artdeco-list__item")
            if elements:
                education_elements = elements
        except:
            pass
            
        if not education_elements:
            try:
                elements = education_section.find_elements(By.XPATH, ".//div[contains(@class, 'pvs-entity')]")
                if elements:
                    education_elements = elements
            except:
                pass
                
        # Przetwórz każdy element wykształcenia
        for edu_element in education_elements:
            try:
                education_item = {}
                
                # Nazwa uczelni
                school_elements = edu_element.find_elements(
                    By.XPATH, 
                    ".//span[contains(@class, 'hoverable-link-text') or contains(@class, 't-bold')]"
                )
                
                if school_elements and len(school_elements) > 0:
                    education_item["school"] = school_elements[0].text.strip()
                
                # Stopień/kierunek
                degree_elements = edu_element.find_elements(
                    By.XPATH, 
                    ".//span[contains(@class, 't-14') and contains(@class, 't-normal')]"
                )
                
                if degree_elements and len(degree_elements) > 0:
                    education_item["degree"] = degree_elements[0].text.strip()
                
                # Daty
                date_elements = edu_element.find_elements(
                    By.XPATH, 
                    ".//span[contains(@class, 't-14') and contains(@class, 't-normal') and contains(@class, 't-black--light')]"
                )
                
                if date_elements and len(date_elements) > 0:
                    for date_elem in date_elements:
                        if "20" in date_elem.text or "19" in date_elem.text:  # Prawdopodobnie zawiera rok
                            education_item["date_range"] = date_elem.text.strip()
                            break
                
                # Dodaj do listy, jeśli udało się znaleźć co najmniej szkołę
                if "school" in education_item:
                    education_items.append(education_item)
                    
            except Exception as e:
                print(f"[WARN] Błąd podczas ekstrahowania wykształcenia: {e}")
                
        return education_items
        
    def extract_skills(self):
        """Ekstrahuje umiejętności"""
        skills = []
        
        # Znajdź sekcję umiejętności
        skills_section = None
        skills_selectors = [
            "section#skills", 
            "section[id='skills']"
        ]
        
        for selector in skills_selectors:
            try:
                skills_section = self.driver.find_element(By.CSS_SELECTOR, selector)
                if skills_section:
                    self.scroll_to_element(skills_section)
                    break
            except:
                pass
                
        if not skills_section:
            return skills
            
        # Znajdź przyciski "Pokaż wszystkie umiejętności"
        show_all_buttons = skills_section.find_elements(
            By.XPATH, 
            ".//a[contains(text(), 'Pokaż wszystkie') or contains(text(), 'Show all')]"
        )
        
        for btn in show_all_buttons:
            try:
                self.scroll_to_element(btn)
                self.driver.execute_script("arguments[0].click();", btn)
                random_delay(1.5, 2.5)
                
                # Po kliknięciu powinno otworzyć się okno modalne z pełną listą umiejętności
                modal_skills = self.driver.find_elements(
                    By.XPATH, 
                    "//div[contains(@class, 'artdeco-modal__content')]//span[contains(@class, 't-bold')]"
                )
                
                for skill in modal_skills:
                    skill_text = skill.text.strip()
                    if skill_text and skill_text not in skills:
                        skills.append(skill_text)
                        
                # Zamknij modal
                close_button = self.driver.find_element(
                    By.XPATH, 
                    "//button[contains(@class, 'artdeco-modal__dismiss')]"
                )
                
                if close_button:
                    self.driver.execute_script("arguments[0].click();", close_button)
                    random_delay(1, 2)
                    
                return skills
            except Exception as e:
                print(f"[WARN] Błąd podczas otwierania wszystkich umiejętności: {e}")
        
        # Jeśli nie udało się otworzyć modalnego okna, spróbuj pobrać umiejętności bezpośrednio z profilu
        try:
            skill_elements = skills_section.find_elements(
                By.XPATH, 
                ".//span[contains(@class, 't-bold') or contains(@class, 'hoverable-link-text')]"
            )
            
            for skill in skill_elements:
                skill_text = skill.text.strip()
                if skill_text and skill_text not in skills:
                    skills.append(skill_text)
                    
        except Exception as e:
            print(f"[WARN] Błąd podczas ekstrahowania umiejętności z profilu: {e}")
            
        return skills
        
    def extract_languages(self):
        """Ekstrahuje języki"""
        languages = []
        
        # Znajdź sekcję języków
        languages_section = None
        languages_selectors = [
            "section#languages", 
            "section[id='languages']"
        ]
        
        for selector in languages_selectors:
            try:
                languages_section = self.driver.find_element(By.CSS_SELECTOR, selector)
                if languages_section:
                    self.scroll_to_element(languages_section)
                    break
            except:
                pass
                
        if not languages_section:
            return languages
            
        # Pobierz wszystkie języki
        try:
            language_elements = languages_section.find_elements(
                By.XPATH, 
                ".//li[contains(@class, 'artdeco-list__item')]"
            )
            
            if not language_elements:
                language_elements = languages_section.find_elements(
                    By.XPATH, 
                    ".//div[contains(@class, 'pvs-entity')]"
                )
                
            for lang_element in language_elements:
                try:
                    language_info = {}
                    
                    # Nazwa języka
                    name_elements = lang_element.find_elements(
                        By.XPATH, 
                        ".//span[contains(@class, 't-bold')]"
                    )
                    
                    if name_elements and len(name_elements) > 0:
                        language_info["name"] = name_elements[0].text.strip()
                        
                    # Poziom znajomości
                    level_elements = lang_element.find_elements(
                        By.XPATH, 
                        ".//span[contains(@class, 't-14') and contains(@class, 't-normal') and contains(@class, 't-black--light')]"
                    )
                    
                    if level_elements and len(level_elements) > 0:
                        language_info["proficiency"] = level_elements[0].text.strip()
                        
                    if "name" in language_info:
                        languages.append(language_info)
                        
                except Exception as e:
                    print(f"[WARN] Błąd podczas ekstrahowania języka: {e}")
                    
        except Exception as e:
            print(f"[WARN] Błąd podczas ekstrahowania języków: {e}")
            
        return languages
        
    def extract_certifications(self):
        """Ekstrahuje certyfikaty"""
        certifications = []
        
        # Znajdź sekcję certyfikatów
        cert_section = None
        cert_selectors = [
            "section#certifications", 
            "section[id='certifications']",
            "section#licenses_and_certifications",
            "section[id='licenses_and_certifications']"
        ]
        
        for selector in cert_selectors:
            try:
                cert_section = self.driver.find_element(By.CSS_SELECTOR, selector)
                if cert_section:
                    self.scroll_to_element(cert_section)
                    break
            except:
                pass
                
        if not cert_section:
            return certifications
            
        # Pobierz wszystkie certyfikaty
        try:
            cert_elements = cert_section.find_elements(
                By.XPATH, 
                ".//li[contains(@class, 'artdeco-list__item')]"
            )
            
            if not cert_elements:
                cert_elements = cert_section.find_elements(
                    By.XPATH, 
                    ".//div[contains(@class, 'pvs-entity')]"
                )
                
            for cert_element in cert_elements:
                try:
                    cert_info = {}
                    
                    # Nazwa certyfikatu
                    name_elements = cert_element.find_elements(
                        By.XPATH, 
                        ".//span[contains(@class, 't-bold')]"
                    )
                    
                    if name_elements and len(name_elements) > 0:
                        cert_info["name"] = name_elements[0].text.strip()
                        
                    # Wydawca
                    issuer_elements = cert_element.find_elements(
                        By.XPATH, 
                        ".//span[contains(@class, 't-14') and contains(@class, 't-normal')]"
                    )
                    
                    if issuer_elements and len(issuer_elements) > 0:
                        cert_info["issuer"] = issuer_elements[0].text.strip()
                        
                    # Data wydania
                    date_elements = cert_element.find_elements(
                        By.XPATH, 
                        ".//span[contains(@class, 't-14') and contains(@class, 't-normal') and contains(@class, 't-black--light')]"
                    )
                    
                    if date_elements and len(date_elements) > 0:
                        for date_elem in date_elements:
                            if "20" in date_elem.text or "19" in date_elem.text:  # Prawdopodobnie zawiera rok
                                cert_info["date"] = date_elem.text.strip()
                                break
                        
                    if "name" in cert_info:
                        certifications.append(cert_info)
                        
                except Exception as e:
                    print(f"[WARN] Błąd podczas ekstrahowania certyfikatu: {e}")
                    
        except Exception as e:
            print(f"[WARN] Błąd podczas ekstrahowania certyfikatów: {e}")
            
        return certifications
        
    def parse_profile(self, profile_url):
        """Parsuje profil LinkedIn i zwraca dane w formacie JSON"""
        print(f"[INFO] Parsowanie profilu: {profile_url}")
        
        try:
            # Przejdź do strony profilu
            self.driver.get(profile_url)
            random_delay(3, 5)
            
            # Załaduj całą stronę i rozwiń wszystkie sekcje
            self.load_full_page()
            self.expand_all_sections()
            
            # Zbierz wszystkie dane
            profile_data = {
                "profile_url": profile_url,
                "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "basic_info": self.extract_basic_info(),
                "about": self.extract_about_section(),
                "experience": self.extract_experience(),
                "education": self.extract_education(),
                "skills": self.extract_skills(),
                "languages": self.extract_languages(),
                "certifications": self.extract_certifications()
            }
            
            # Zapisz do pliku JSON
            filename = f"{profile_url.split('/')[-2]}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, ensure_ascii=False, indent=2)
                
            print(f"[INFO] Dane profilu zapisane do pliku: {filename}")
            
            return profile_data
            
        except Exception as e:
            print(f"[ERROR] Błąd podczas parsowania profilu {profile_url}: {e}")
            return None


class ProfileScraperThread(threading.Thread):
    def __init__(self, thread_id, profile_queue, driver_factory):
        threading.Thread.__init__(self)
        self.thread_id = thread_id
        self.profile_queue = profile_queue
        self.driver_factory = driver_factory
        
    def run(self):
        print(f"[INFO] Wątek {self.thread_id} rozpoczyna pracę")
        
        # Utworzenie nowego drivera dla wątku
        driver = self.driver_factory.create_chrome_driver()
        
        try:
            # Logowanie - każdy wątek musi zalogować się oddzielnie
            login_handler = LinkedInLoginHandler(driver)
            driver.get("https://www.linkedin.com/login")
            random_delay(2, 4)
            
            if not login_handler.login(EMAIL, PASSWORD):
                print(f"[ERROR] Wątek {self.thread_id} nie mógł się zalogować")
                return
                
            print(f"[INFO] Wątek {self.thread_id} zalogował się")
            
            # Inicjalizacja parsera
            profile_parser = LinkedInProfileParser(driver)
            
            # Pobieraj profile z kolejki, dopóki są dostępne
            while not self.profile_queue.empty():
                try:
                    profile_url = self.profile_queue.get(block=False)
                    print(f"[INFO] Wątek {self.thread_id} przetwarza profil: {profile_url}")
                    
                    # Parsuj profil
                    profile_data = profile_parser.parse_profile(profile_url)
                    
                    # Oznacz zadanie jako zakończone
                    self.profile_queue.task_done()
                    
                    # Dodaj losowe opóźnienie między profilami
                    random_delay(3, 7)
                    
                except queue.Empty:
                    break
                except Exception as e:
                    print(f"[ERROR] Wątek {self.thread_id} napotkał błąd: {e}")
                    self.profile_queue.task_done()
                    
        except Exception as e:
            print(f"[ERROR] Wątek {self.thread_id} napotkał błąd: {e}")
        finally:
            driver.quit()
            print(f"[INFO] Wątek {self.thread_id} zakończył pracę")


def main():
    driver = None
    try:
        # Pobierz wybór akcji
        print("Wybierz akcję:")
        print("1. Usuwanie komentarzy (delete-comment)")
        print("2. Wyszukiwanie osób (find-people)")
        print("3. Parsowanie profili LinkedIn (parse-profiles)")
        action = input("Wybierz akcję (1/2/3): ").strip()
        
        if action == "3" or action.lower() == "parse-profiles":
            # Parsowanie profili LinkedIn
            urls_input = input("Podaj URL-e profili LinkedIn oddzielone przecinkami: ").strip()
            profile_urls = [url.strip() for url in urls_input.split(",")]
            
            if not profile_urls:
                print("[ERROR] Nie podano żadnych URL-i")
                return
                
            # Utwórz kolejkę z URL-ami profili
            profile_queue = queue.Queue()
            for url in profile_urls:
                profile_queue.put(url)
                
            # Określ liczbę wątków (można dostosować)
            num_threads = min(3, len(profile_urls))
            
            # Utwórz i uruchom wątki
            threads = []
            for i in range(num_threads):
                thread = ProfileScraperThread(i+1, profile_queue, DriverFactory)
                threads.append(thread)
                thread.start()
                
            # Czekaj, aż wszystkie wątki zakończą pracę
            for thread in threads:
                thread.join()
                
            print("[INFO] Zakończono parsowanie profili")
            return
            
        # Dla pozostałych akcji użyj standardowego flow
        driver = DriverFactory.create_chrome_driver()
        
        # Zaloguj się na LinkedIn
        login_handler = LinkedInLoginHandler(driver)
        driver.get(PROFILE_URL)
        random_delay(1, 3)
        
        if not login_handler.login(EMAIL, PASSWORD):
            print("[ERROR] Logowanie nie powiodło się")
            return
            
        print("[INFO] Zalogowano pomyślnie.")
        
        # Wykonaj wybraną akcję
        if action == "1" or action.lower() == "delete-comment":
            # Usuwanie komentarzy
            comment_handler = LinkedInCommentHandler(driver)
            comment_handler.find_and_delete_comments()
        elif action == "2" or action.lower() == "find-people":
            # Wyszukiwanie osób
            search_query = input("Podaj frazę wyszukiwania (np. 'Security Engineer'): ").strip()
            
            # Utwórz handler wyszukiwania z automatycznie generowaną nazwą pliku
            people_handler = LinkedInPeopleSearchHandler(driver, search_query)
            profiles = people_handler.search_and_collect_profiles()
            
            # Wyświetl podsumowanie
            if profiles:
                print(f"\n[INFO] Zapisano {len(profiles)} profili do pliku {people_handler.csv_filename}")
        else:
            print("[ERROR] Nieznana akcja")

        input("Naciśnij Enter, aby zamknąć przeglądarkę...")
    except Exception as e:
        print(f"[FATAL] Wystąpił nieoczekiwany błąd: {e}")
    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    main()