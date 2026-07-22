from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service
import time
import csv

service = Service("msedgedriver.exe")
driver = webdriver.Edge(service=service)
driver.maximize_window()
driver.get("https://www.flipkart.com/helpcentre")
time.sleep(5)

# Open CSV file once at the beginning
csv_file = open("flipkart_helpcentre.csv", "w", newline="", encoding="utf-8")
writer = csv.writer(csv_file)
writer.writerow(["Topic", "Question", "Answer"])  # Header row


###############FUNTIONS####################
def click_view_more():
    #Click the View More option to view all the questions  
    view_more= driver.find_elements(By.XPATH, "//div[@class='GsrJy8 FSDx4Q']//span[text()='View More']")
    print("View More elements found:", len(view_more))
    if view_more:
        view_more[0].click()
        time.sleep(1)

def extract_questions():
    # Return all question elements under the current topic/subtopic.
    return driver.find_elements(By.XPATH, "//div[@class='aL22KS U0-tcY FSDx4Q']//p")

def handle_questions(main_topic):
    click_view_more()  # Ensure all questions are visible
    questions = extract_questions()
    num_questions = len(questions)
    print(f"Number of questions: {num_questions}")
    for q_index in range(num_questions):
        click_view_more()
        questions = extract_questions()
        q= questions[q_index]
        q_text = q.text.strip()
        if q_text:
            print(f"\t{q_index + 1}.Q:", q_text)
            try:
                q.click()
                time.sleep(3)

                answer = driver.find_element(By.XPATH, "//div[contains(@class,'aL22KS OHsQKd')]").text
                print(f"\t{q_index + 1}. A:", answer)
                writer.writerow([main_topic, q_text, answer])

                driver.back()
                time.sleep(2)
            except Exception as e:
                print("   Error fetching answer:", e)

def handle_subtopics(topic):
    try:
  # Wait for the subtopics to load
        subtopics = topic.find_element(By.XPATH, "./following-sibling::div[contains(@class,'Z1CARP')]").find_elements(By.TAG_NAME, "span")
        for sub_topic_index in range(len(subtopics)):
            subtopics = topic.find_element(By.XPATH, "./following-sibling::div[contains(@class,'Z1CARP')]").find_elements(By.TAG_NAME, "span")
            sub = subtopics[sub_topic_index]
            sub_name = sub.text.strip()
            if sub_name:
                print(f"\n   └── Subtopic: {sub_name}")
                sub.click()
                time.sleep(1)
                handle_questions(sub_name)  # Handle questions for the subtopic

    except:
        pass
        
##############################################################################       

# Get all main topics under Help Topics
main_topics = driver.find_elements(By.XPATH,"//span[text()='Help Topics']/following::div[contains(@class,'-0XXWT') and contains(@class,'_63VJT3')]")

for topic_index in range(len(main_topics)):
    # Refetch topics after page reload
    main_topics = driver.find_elements(By.XPATH,"//span[text()='Help Topics']/following::div[contains(@class,'-0XXWT') and contains(@class,'_63VJT3')]")
    topic = main_topics[topic_index]
    topic_name = topic.text.strip()
    print("\n##################################")
    print(f"{topic_index + 1}. Main Topic: {topic_name}")
    topic.click()
    time.sleep(1)

    handle_questions(topic_name)  # Handle questions for the main topic
    handle_subtopics(topic)  # Handle subtopics of the main topics

driver.quit()



# ---------- CLOSE ----------
csv_file.close()
driver.quit()
print("\n✅ Data saved to flipkart_helpcentre.csv")