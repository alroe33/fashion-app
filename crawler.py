import time
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def get_musinsa_image_first(url, limit=5):
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    # 차단 방지를 위한 헤더 설정
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    print(f"\n🚀 [접속 시도] {url}")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    items = []
    try:
        driver.get(url)
        time.sleep(4) # 로딩 대기

        # 스크롤 다운 (이미지 로딩)
        print("스크롤을 내립니다...")
        for i in range(1, 4):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3 * arguments[0]);", i)
            time.sleep(0.5)

        # 1. 페이지 내의 모든 이미지 태그를 찾습니다.
        print("📸 이미지 태그 탐색 중...")
        images = driver.find_elements(By.TAG_NAME, "img")
        print(f"   -> 발견된 이미지 개수: {len(images)}개")

        count = 0
        seen_links = set()

        for img in images:
            if count >= limit:
                break
            
            try:
                # 이미지 주소 가져오기
                img_src = img.get_attribute("src")
                if not img_src:
                    img_src = img.get_attribute("data-original")
                
                # 의미 없는 작은 아이콘이나 로고는 건너뜀 (크기나 주소로 필터링)
                if not img_src or "icon" in img_src or "logo" in img_src:
                    continue

                # 2. 이미지의 부모(링크) 찾기
                # 이미지를 감싸고 있는 가장 가까운 <a> 태그를 찾습니다.
                try:
                    parent_link = img.find_element(By.XPATH, "./ancestor::a")
                    link_href = parent_link.get_attribute("href")
                except:
                    # 링크가 없으면 상품이 아님
                    continue

                # 링크가 없거나, 자바스크립트 링크면 건너뜀
                if not link_href or "javascript" in link_href:
                    continue

                # 중복 확인
                if link_href in seen_links:
                    continue

                # 3. 텍스트 정보 가져오기
                # 링크 안의 텍스트가 없으면 이미지의 alt 속성 사용
                text = parent_link.text.strip()
                if not text:
                    text = img.get_attribute("alt")
                
                # 텍스트 정리 (줄바꿈 등)
                lines = text.split('\n')
                brand = "추천 브랜드"
                name = "상품 정보 없음"

                if len(lines) >= 2:
                    brand = lines[0]
                    name = lines[1]
                elif len(lines) == 1:
                    name = lines[0]
                else:
                    # 텍스트가 아예 없으면 URL의 일부를 이름으로 임시 사용
                    name = "상품 상세 보기"

                # 저장
                items.append({
                    "brand": brand,
                    "name": name,
                    "img": img_src,
                    "link": link_href
                })
                seen_links.add(link_href)
                count += 1
                print(f"  ✅ [수집 성공] {name}")

            except Exception:
                continue

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
    finally:
        driver.quit()

    return items

# --- 실행 ---
if __name__ == "__main__":
    
    print("\n[1/2] 상의 데이터 수집")
    top_url = "https://www.musinsa.com/category/001?gf=A&sortCode=POPULAR"
    tops = get_musinsa_image_first(top_url, limit=5)
    
    print("\n[2/2] 하의 데이터 수집")
    bottom_url = "https://www.musinsa.com/category/003?gf=A"
    bottoms = get_musinsa_image_first(bottom_url, limit=5)

    final_data = {"tops": tops, "bottoms": bottoms}
    
    print("\n" + "="*50)
    print("👇 결과 데이터 (HTML에 붙여넣으세요) 👇")
    print("="*50)
    print(json.dumps(final_data, ensure_ascii=False, indent=4))
    print("="*50)