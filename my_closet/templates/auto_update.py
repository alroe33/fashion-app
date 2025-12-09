import time
import json
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# --- 크롤링 함수 ---
def get_musinsa_data(url, limit=50):
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    # chrome_options.add_argument("--headless") # 브라우저 창 숨기기

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    items = []
    try:
        driver.get(url)
        time.sleep(3)

        print(f"⬇️ 스크롤을 내리며 {limit}개의 상품을 찾습니다...")
        for i in range(1, 10): 
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 10 * arguments[0]);", i)
            time.sleep(0.5)

        images = driver.find_elements(By.TAG_NAME, "img")
        
        count = 0
        seen_links = set()

        for img in images:
            if count >= limit: break
            try:
                img_src = img.get_attribute("src")
                if not img_src: img_src = img.get_attribute("data-original")
                if not img_src or "icon" in img_src or "logo" in img_src: continue

                parent_link = img.find_element(By.XPATH, "./ancestor::a")
                link_href = parent_link.get_attribute("href")
                
                if not link_href or "javascript" in link_href or link_href in seen_links: continue

                text = parent_link.text.strip()
                if not text: text = img.get_attribute("alt")
                lines = text.split('\n')
                
                brand = lines[0] if lines else "Brand"
                name = lines[1] if len(lines) > 1 else (lines[0] if lines else "상품명 없음")

                items.append({"brand": brand, "name": name, "img": img_src, "link": link_href})
                seen_links.add(link_href)
                count += 1
                
            except: continue
            
    except Exception as e:
        print(f"크롤링 에러: {e}")
    finally:
        driver.quit()
    
    return items

# --- HTML 업데이트 함수 ---
def update_html_file(file_path, new_data):
    print(f"📂 파일 업데이트 중: {os.path.abspath(file_path)}")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ 오류: '{file_path}' 파일을 찾을 수 없습니다.")
        return

    start_marker = "// DATA_START"
    end_marker = "// DATA_END"

    if start_marker not in content or end_marker not in content:
        print("❌ 오류: index.html 표식 없음!")
        return

    json_str = json.dumps(new_data, ensure_ascii=False, indent=4)
    new_code = f"const dataDB = {json_str};"

    parts = content.split(start_marker)
    new_content = parts[0] + start_marker + "\n" + new_code + "\n        " + end_marker + parts[1].split(end_marker)[1]

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"\n✨ 데이터 업데이트 성공! ✨")

# --- 실행 ---
if __name__ == "__main__":
    print("🚀 상의/하의 데이터 수집 시작...")

    # 상의(001)와 하의(003) 각각 50개씩 수집
    top_url = "https://www.musinsa.com/category/001?gf=A&sortCode=POPULAR"
    bottom_url = "https://www.musinsa.com/category/003?gf=A"
    
    tops = get_musinsa_data(top_url, limit=50)
    print(f"✅ 상의 {len(tops)}개 완료")
    
    bottoms = get_musinsa_data(bottom_url, limit=50)
    print(f"✅ 하의 {len(bottoms)}개 완료")
    
    final_data = {"tops": tops, "bottoms": bottoms}

    html_file = os.path.join("templates", "index.html") 
    update_html_file(html_file, final_data)