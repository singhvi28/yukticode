import time
import uuid
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium.webdriver.chrome.service import Service

def get_driver():
    options = webdriver.ChromeOptions()
    options.binary_location = '/usr/bin/chromium-browser'
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    service = Service('/usr/bin/chromedriver')
    driver = webdriver.Chrome(service=service, options=options)
    driver.implicitly_wait(10)
    return driver

# Wait explicitly for elements
def wait_for_element(driver, by, value, timeout=10):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, value))
    )

def wait_for_text(driver, by, value, text, timeout=20):
    return WebDriverWait(driver, timeout).until(
        EC.text_to_be_present_in_element((by, value), text)
    )

def run_tests():
    driver = get_driver()
    base_url = "http://localhost:5173"
    
    unique_suffix = str(uuid.uuid4())[:8]
    username = f"test_{unique_suffix}"
    email = f"test_{unique_suffix}@example.com"
    password = "password123"

    try:
        # 1. Register
        print(f"Registering as {username}...")
        driver.get(f"{base_url}/register")
        driver.find_element(By.NAME, "username").send_keys(username)
        driver.find_element(By.NAME, "email").send_keys(email)
        driver.find_element(By.NAME, "password").send_keys(password)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(2) # wait for redirect

        # 2. Login
        print("Logging in...")
        driver.get(f"{base_url}/login")
        driver.find_element(By.NAME, "username").send_keys(username)
        driver.find_element(By.NAME, "password").send_keys(password)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        
        # Wait until we are redirected or login succeeds
        wait_for_element(driver, By.CSS_SELECTOR, "a[href='/problems']")
        print("Login successful.")

        # Test cases: Language, Expected Verdict, Code
        tests = [
            ("cpp", "AC", "#include <iostream>\nusing namespace std;\nint main() { int t; cin >> t; while(t--) { int n; cin >> n; cout << \"1 2\\n\"; } return 0; }"),
            ("cpp", "RE", "#include <iostream>\nusing namespace std;\nint main() { int* p = nullptr; *p = 1; return 0; }"),
            ("py", "TLE", "while True: pass"),
            ("java", "AC", "import java.util.Scanner;\npublic class Main {\n    public static void main(String[] args) {\n        Scanner scanner = new Scanner(System.in);\n        if (scanner.hasNextInt()) {\n            int t = scanner.nextInt();\n            for (int i = 0; i < t; i++) {\n                if (scanner.hasNextInt()) {\n                    int n = scanner.nextInt();\n                    System.out.println(\"1 2\");\n                }\n            }\n        }\n    }\n}\n")
        ]

        # 3. Submit codes for Problem 1
        problem_id = 1
        print(f"Navigating to problem {problem_id}...")
        driver.get(f"{base_url}/problems/{problem_id}")
        
        # We need to wait for the editor to load
        wait_for_element(driver, By.CSS_SELECTOR, ".editor-container")
        print("Editor loaded.")

        for lang, expected_verdict, code in tests:
            print(f"\n--- Testing {lang} ({expected_verdict}) ---")
            
            # Select language
            lang_select = driver.find_element(By.TAG_NAME, "select")
            for option in lang_select.find_elements(By.TAG_NAME, "option"):
                if option.get_attribute("value") == lang:
                    option.click()
                    break

            # The editor is deeply nested / might be Monaco or simple textarea.
            # Assuming it's a textarea or we can execute JS to set value
            # Since React controls the textarea, we use JavaScript to set the value.
            # Let's try locating the textarea handling the code.
            
            # The app likely uses a custom editor, let's inject text via JS if it's Monaco or use simple sending
            text_area = driver.find_element(By.CSS_SELECTOR, ".editor-container textarea")
            
            # Clear existing text 
            driver.execute_script("arguments[0].value = '';", text_area)
            # Send new code
            text_area.send_keys(code)
            
            # Click submit
            submit_btn = driver.find_element(By.CSS_SELECTOR, "button.submit-btn")
            submit_btn.click()
            print("Submitted. Waiting for verdict...")

            # Wait for verdict badge
            # It starts as "PENDING", then changes to AC, RE, TLE etc.
            badge = wait_for_element(driver, By.CSS_SELECTOR, ".status-badge")
            
            # Wait until text is NOT Pending
            WebDriverWait(driver, 30).until(
                lambda d: d.find_element(By.CSS_SELECTOR, ".status-badge").text != "PENDING"
            )
            
            final_verdict = driver.find_element(By.CSS_SELECTOR, ".status-badge").text
            print(f"Final Verdict: {final_verdict}")
            
            if final_verdict != expected_verdict:
                print(f"❌ FAILED. Expected {expected_verdict}, got {final_verdict}")
            else:
                print(f"✅ PASSED. Got expected {expected_verdict}")
            
            time.sleep(1) # wait a tiny bit before next submission

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    run_tests()
