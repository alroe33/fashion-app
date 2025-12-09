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
LOCATION = "us-central1"
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

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
    try:
        # 데이터 받기 (파일 저장 안 함!)
        model_file = request.files['model_image']
        top_url = request.form.get('top_url')
        bottom_url = request.form.get('bottom_url')

        # 1. 이미지를 메모리에서 바로 PIL로 변환
        user_img = Image.open(model_file)
        
        gemini_inputs = [user_img]
        clothes_desc = ""

        if top_url and top_url != 'null':
            # requests로 이미지 바이트 가져와서 바로 열기
            top_bytes = BytesIO(requests.get(top_url).content)
            gemini_inputs.append(Image.open(top_bytes))
            clothes_desc += " - User wears the TOP image."

        if bottom_url and bottom_url != 'null':
            bottom_bytes = BytesIO(requests.get(bottom_url).content)
            gemini_inputs.append(Image.open(bottom_bytes))
            clothes_desc += " - User wears the BOTTOM image."

        # 2. Gemini 프롬프트 생성
        gemini_model = genai.GenerativeModel('gemini-2.5-flash')
        system_instruction = f"""
        Describe Image 1 (User) in extreme detail (Body, Pose, Face).
        Then describe the clothes.
        Create a prompt for Imagen 3 starting with "A high-quality full-body fashion photo of...".
        {clothes_desc}
        """
        full_inputs = [system_instruction] + gemini_inputs
        response = gemini_model.generate_content(full_inputs)
        generated_prompt = response.text

        # 3. Imagen 생성
        imagen_model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")
        images = imagen_model.generate_images(
            prompt=generated_prompt,
            number_of_images=1,
            aspect_ratio="9:16",
            person_generation="allow_adult",
            safety_filter_level="block_some"
        )
# 1) 임시 파일명 생성
        temp_filename = f"temp_{current_user.id}_{int(time.time())}.png"
        
        # 2) 파일로 저장 (여기서는 format 옵션을 쓰지 않음!)
        images[0].save(temp_filename) 

        # 3) PIL로 다시 열어서 메모리 버퍼에 담기
        img = Image.open(temp_filename)
        img_io = BytesIO()
        img.save(img_io, format='PNG') # 이제 PIL 객체이므로 format 옵션 사용 가능
        img_io.seek(0)
        
        # 4) Base64 인코딩
        img_base64 = base64.b64encode(img_io.getvalue()).decode('utf-8')
        img_data_url = f"data:image/png;base64,{img_base64}"
        
        # 5) 임시 파일 삭제 (청소)
        try:
            os.remove(temp_filename)
        except:
            pass # 혹시 삭제 못 해도 패스

        return jsonify({'status': 'success', 'image_path': img_data_url})

    except Exception as e:
        print(f"Error: {e}")
        # 에러 나도 임시 파일 있으면 지우기
        if 'temp_filename' in locals() and os.path.exists(temp_filename):
            os.remove(temp_filename)
        return jsonify({'status': 'error', 'message': str(e)})
    

# Vercel을 위한 필수 설정 (이거 없으면 안 돌아감)
# Vercel은 app 객체를 찾아서 실행합니다.
if __name__ == '__main__':
    app.run(debug=True)
