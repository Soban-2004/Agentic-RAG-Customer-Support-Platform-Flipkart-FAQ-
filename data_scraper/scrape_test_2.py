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
csv_file = open("flipkart_helpcentre_2.csv", "w", newline="", encoding="utf-8")
writer = csv.writer(csv_file)
writer.writerow(["Topic", "Question", "Answer"])  # Header row/

tot_q = 0

#Function
def click_view_more():
    #Click the View More option to view all the questions  
    view_more= driver.find_elements(By.XPATH, "//div[@class='GsrJy8 FSDx4Q']//span[text()='View More']")
    view_more[0].click() if view_more else None
    time.sleep(1)

def extract_questions():
    raw_questions = driver.find_elements(By.XPATH, "//div[@class='aL22KS U0-tcY FSDx4Q']//p")
    # Filter out blanks
    return [q for q in raw_questions if q.text.strip()]


def handle_questions(topic_name):
        questions = extract_questions()
        q = questions[q_index]
        q_text = q.text.strip()
        if q_text:
            print(f"\t{q_index + 1}.Q:", q_text)
            try:
                q.click()
                time.sleep(3)

                answer = driver.find_element(By.XPATH, "//div[contains(@class,'aL22KS OHsQKd')]").text
                print(f"\t{q_index + 1}. A:", answer)
                writer.writerow([topic_name, q_text, answer])

                driver.back()
                time.sleep(2)
            except Exception as e:
                print("   Error fetching answer:", e)


# Get all main topics under Help Topics
main_topics = driver.find_elements(By.XPATH,"//span[text()='Help Topics']/following::div[contains(@class,'-0XXWT') and contains(@class,'_63VJT3')]")

for topic_index in range(4,len(main_topics)):
    # Refetch topics after page reload
    main_topics = driver.find_elements(By.XPATH,"//span[text()='Help Topics']/following::div[contains(@class,'-0XXWT') and contains(@class,'_63VJT3')]")
    topic = main_topics[topic_index]
    topic_name = topic.text.strip()
    print("\n##################################")
    print(f"{topic_index + 1}. Main Topic: {topic_name}")
    topic.click()
    time.sleep(1)

    click_view_more()

    # Get questions **once before inner loop**
    questions = extract_questions()
    num_questions = len(questions)
    print(f"Number of questions: {num_questions}")
    tot_q += num_questions

    for q_index in range(num_questions):

        click_view_more()
        handle_questions(topic_name=topic_name)


    # Check if it has subtopics (Z1CARP class nearby)
    try:
  # Wait for the subtopics to load
        subtopics = topic.find_element(By.XPATH, "./following-sibling::div[contains(@class,'Z1CARP')]").find_elements(By.TAG_NAME, "span")
        for sub_topic_index in range(len(subtopics)):
            subtopics = topic.find_element(By.XPATH, "./following-sibling::div[contains(@class,'Z1CARP')]").find_elements(By.TAG_NAME, "span")
            sub = subtopics[sub_topic_index]
            sub_name = sub.text.strip()
            if sub_name:
                print(f"\n   └── Subtopic: {sub_name}")
                sub.click()  # Click to expand if needed
                time.sleep(1) 

                click_view_more()

                # Collect all questions under this topic
                questions = extract_questions()
                num_s_questions = len(questions)
                print(f"Number of questions: {num_s_questions}")
                tot_q += num_s_questions
                for q_index in range(num_s_questions):

                    click_view_more()
                    handle_questions(topic_name=sub_name)  # Handle questions for the subtopic

                    
    except:
        pass


print(f"Total questions extracted: {tot_q}")
driver.quit()
# ---------- CLOSE ----------
csv_file.close()

print("\n✅ Data saved to flipkart_helpcentre.csv")


