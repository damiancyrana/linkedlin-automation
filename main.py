"""
LinkedIn Bot - Main Module
"""
import traceback
from abc import ABC, abstractmethod

from login import Config, LoggerSetup, DriverFactory, LinkedInLoginHandler, Utils
from delete_comments import LinkedInCommentHandler
from find_people import LinkedInPeopleSearchHandler


# Command Pattern implementation
class Command(ABC):
    """Abstract command interface"""
    @abstractmethod
    def execute(self):
        pass


class DeleteCommentsCommand(Command):
    def __init__(self, driver):
        self.driver = driver
        self.logger = LoggerSetup.get_logger("DeleteCommentsCommand")
        
    def execute(self):
        self.logger.info("Executing delete comments command")
        comment_handler = LinkedInCommentHandler(self.driver)
        comment_handler.find_and_delete_comments()
        return "Comments deletion completed"


class FindPeopleCommand(Command):
    def __init__(self, driver, search_query):
        self.driver = driver
        self.search_query = search_query
        self.logger = LoggerSetup.get_logger("FindPeopleCommand")
        
    def execute(self):
        self.logger.info(f"Executing find people command for query: {self.search_query}")
        people_handler = LinkedInPeopleSearchHandler(self.driver, self.search_query)
        profiles = people_handler.search_and_collect_profiles()
        return f"Found {len(profiles)} profiles. Data saved to {people_handler.json_filename}"


# Command invoker
class LinkedInCommandInvoker:
    def __init__(self, driver):
        self.driver = driver
        self.logger = LoggerSetup.get_logger("LinkedInCommandInvoker")
        
    def execute_command(self, command):
        self.logger.info(f"Invoking command: {command.__class__.__name__}")
        try:
            result = command.execute()
            self.logger.info(f"Command executed successfully: {result}")
            return result
        except Exception as e:
            self.logger.error(f"Command execution failed: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return f"Command execution failed: {str(e)}"


def main():
    logger = LoggerSetup.get_logger("Main")
    driver = None
    try:
        # Get action choice
        print("Choose action:")
        print("1. Delete comments")
        print("2. Find people")
        action = input("Select action (1/2): ").strip()
        
        # Create browser driver
        driver = DriverFactory.create_chrome_driver()
        logger.info("Chrome browser launched")
        
        # Go to LinkedIn login page
        driver.get("https://www.linkedin.com/login")
        Utils.random_delay(2, 4)
        
        # Check if page loaded
        current_url = driver.current_url
        logger.info(f"Page loaded: {current_url}")
        
        # Login to LinkedIn
        login_handler = LinkedInLoginHandler(driver)
        
        if not login_handler.login(Config.EMAIL, Config.PASSWORD):
            logger.error("Login failed")
            return
        
        # Create command invoker
        invoker = LinkedInCommandInvoker(driver)
        
        # Execute selected action using Command pattern
        if action == "1" or action.lower() == "delete-comment":
            # Delete comments command
            command = DeleteCommentsCommand(driver)
            invoker.execute_command(command)
        elif action == "2" or action.lower() == "find-people":
            # Find people command
            search_query = input("Enter search phrase (e.g. 'Security Engineer'): ").strip()
            command = FindPeopleCommand(driver, search_query)
            invoker.execute_command(command)
        else:
            logger.error("Unknown action")

        input("Press Enter to close the browser...")
    except Exception as e:
        logger.critical(f"Unexpected error occurred: {e}")
        logger.critical(f"Error details:\n{traceback.format_exc()}")
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Browser has been closed")
            except Exception as qe:
                logger.error(f"Problem closing browser: {qe}")


if __name__ == "__main__":
    main()