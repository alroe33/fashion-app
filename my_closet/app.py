from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os
import requests
import json
import base64
import pymysql
import time
from io import BytesIO
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image

# 구글 AI
import google.generativeai as genai
from vertexai.preview.vision_models import ImageGenerationModel
import vertexai
from google.oauth2 import service_account

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key')

# --- 1. 클라우드 DB 설정 (환경 변수 사용) ---
def get_db_connection():
    return pymysql.connect(
        host=os.environ.get('DB_HOST'),
        user=os.environ.get('DB_USER'),
        password=os.environ.get('DB_PASSWORD'),
        db=os.environ.get('DB_NAME'), # fashion_app 인지 확인
        port=4000,
        charset='utf8mb4',
        # pymysql에서는 ssl_mode 대신 ssl 딕셔너리만 쓰면 됩니다.
        # Render 서버에는 이 경로에 인증서가 이미 있습니다.
        ssl={'ca': '/etc/ssl/certs/ca-certificates.crt'}
    )

# --- 2. 구글 인증 (JSON 파일 내용을 환경변수에서 읽기) ---
# Vercel 환경변수 'GOOGLE_CREDENTIALS_JSON'에 파일 내용을 통째로 넣을 예정
google_creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
creds_dict = json.loads(google_creds_json) if google_creds_json else {}

PROJECT_ID = creds_dict.get("project_id")
LOCATION = "us-west1"
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
STATIC_FOLDER = 'static'
TEMP_FOLDER = os.path.join(STATIC_FOLDER, 'temp')
os.makedirs(TEMP_FOLDER, exist_ok=True) # 폴더가 없으면 알아서 만듦
try:
    if creds_dict:
        my_credentials = service_account.Credentials.from_service_account_info(creds_dict)
        vertexai.init(project=PROJECT_ID, location=LOCATION, credentials=my_credentials)
        genai.configure(api_key=GEMINI_API_KEY)
        print("✅ 구글 AI 연결 성공")
except Exception as e:
    print(f"❌ 구글 AI 연결 실패: {e}")

# --- 로그인 설정 ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, username FROM users WHERE id = %s", (user_id,))
        res = cur.fetchone()
        conn.close()
        if res: return User(id=res[0], username=res[1])
    except:
        return None
    return None

# --- 라우트 ---
@app.route('/')
@login_required
def home():
    return render_template('index.html', username=current_user.username)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT id, username, password FROM users WHERE username = %s", (username,))
            user_data = cur.fetchone()
            conn.close()
            if user_data and check_password_hash(user_data[2], password):
                user = User(id=user_data[0], username=user_data[1])
                login_user(user)
                return redirect(url_for('home'))
            else:
                flash('로그인 실패')
        except Exception as e:
            flash(f"DB 에러: {str(e)}")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_pw = generate_password_hash(password)
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed_pw))
            conn.commit()
            conn.close()
            flash('가입 성공')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'에러: {str(e)}')
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/generate', methods=['POST'])
@login_required
def generate():
    print("🎨 [서버] 구글 AI 스타일 생성 요청 시작!")

    try:
        # 1. 데이터 받기
        model_file = request.files['model_image']
        top_url = request.form.get('top_url')
        bottom_url = request.form.get('bottom_url')

        # 2. 이미지 준비 (PIL)
        user_img_path = os.path.join(TEMP_FOLDER, f"user_{current_user.id}.jpg")
        model_file.save(user_img_path)
        user_img = Image.open(user_img_path)

        gemini_inputs = [user_img]
        input_role_desc = "Image 1 is the User (Target Model)."

        # 상의 처리
        if top_url and top_url != 'null':
            top_bytes = BytesIO(requests.get(top_url).content)
            gemini_inputs.append(Image.open(top_bytes))
            input_role_desc += " Image 2 is the TOP clothing (Must wear this)."

        # 하의 처리
        if bottom_url and bottom_url != 'null':
            bottom_bytes = BytesIO(requests.get(bottom_url).content)
            gemini_inputs.append(Image.open(bottom_bytes))
            # 이미지가 3개째인지 2개째인지 확인
            img_idx = 3 if (top_url and top_url != 'null') else 2
            input_role_desc += f" Image {img_idx} is the BOTTOM clothing (Must wear this)."

        # 3. [Gemini] 프롬프트 엔지니어링 (옷 묘사 최우선!)
        gemini_model = genai.GenerativeModel('gemini-2.5-flash')
        
        # ▼▼▼ 여기가 핵심! Gemini에게 내리는 아주 구체적인 지령 ▼▼▼
        system_instruction = f"""
        You are a fashion expert creating a prompt for an AI image generator.
        Your goal is to describe the target look so the AI can draw the user wearing the NEW clothes.

        [INPUT IMAGES ROLE]
        {input_role_desc}

        [INSTRUCTIONS]
        Step 1. Analyze the User (Image 1) to preserve identity.
        - Describe their Face, Hairstyle, Body Shape, and Pose in detail.
        - **IMPORTANT: IGNORE the clothes the user is currently wearing in Image 1.**

        Step 2. Analyze the NEW Clothes (Image 2, 3) visually.
        - Look at the provided clothing images closely.
        - Extract details: Color (e.g., 'Baby Blue'), Fabric (e.g., 'Denim'), Pattern (e.g., 'Checkered'), Fit (e.g., 'Oversized'), and distinctive features (e.g., 'Buttons', 'Logo', 'Collar').
        
        Step 3. Construct the Final Prompt.
        - Start with: "A high-quality full-body fashion shot of..."
        - Combine the [User Description] with the [New Clothes Description].
        - Explicitly state: "The user is wearing a [Detailed description of Top] and [Detailed description of Bottom]."
        - Ensure the background matches the vibe of Image 1.
        """
        
        full_inputs = [system_instruction] + gemini_inputs

        print("🧠 [Gemini] 옷 특징 추출 및 프롬프트 작성 중...")
        response = gemini_model.generate_content(full_inputs)
        generated_prompt = response.text
        print(f"📝 [생성된 프롬프트] {generated_prompt}")

        # 4. [Imagen] 이미지 생성 (재시도 로직 포함)
        print("🎨 [Imagen] 이미지 그리는 중...")
        imagen_model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")
        
        images = None
        for attempt in range(3): # 3번 재시도
            try:
                images = imagen_model.generate_images(
                    prompt=generated_prompt,
                    number_of_images=1,
                    aspect_ratio="9:16",
                    person_generation="allow_adult",
                    safety_filter_level="block_some"
                )
                break
            except Exception as e:
                print(f"⚠️ 생성 실패 ({attempt+1}/3): {e}")
                if "429" in str(e): time.sleep(2)
                else: break

        if not images:
            raise Exception("이미지 생성 실패 (서버 혼잡)")

        # 5. 결과 변환 (Base64)
        img_io = BytesIO()
        images[0].save(img_io, format='PNG')
        img_io.seek(0)
        img_base64 = base64.b64encode(img_io.getvalue()).decode('utf-8')
        img_data_url = f"data:image/png;base64,{img_base64}"
        
        return jsonify({'status': 'success', 'image_path': img_data_url})

    except Exception as e:
        print(f"❌ 에러: {e}")
        return jsonify({'status': 'error', 'message': str(e)})

# Vercel을 위한 필수 설정 (이거 없으면 안 돌아감)
# Vercel은 app 객체를 찾아서 실행합니다.
if __name__ == '__main__':
    app.run(debug=True)
