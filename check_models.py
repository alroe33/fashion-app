import google.generativeai as genai

# 본인의 API 키를 입력하세요
genai.configure(api_key="AIzaSyCIQXmwuo_ZmzcEoIdlTy3Gar4cV9d6o24")

print("🔍 사용 가능한 모델 목록을 조회합니다...")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"- {m.name}")
except Exception as e:
    print(f"오류 발생: {e}")