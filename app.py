import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import re
from sqlalchemy import func, cast, Date

app = Flask(__name__)

# DB 설정 (PostgreSQL)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:postgres@localhost:5432/postgres'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Meal(db.Model):
    __tablename__ = 'meal'
    id = db.Column(db.Integer, primary_key=True)
    food_name = db.Column(db.String(100), nullable=False)
    calories = db.Column(db.Integer, nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)

def get_calories_from_naver(food_name):
    """네이버 검색을 통해 음식의 칼로리 정보를 크롤링합니다."""
    # 검색어 뒤에 '칼로리'를 붙여 검색 결과 정확도를 높입니다.
    search_url = f"https://search.naver.com/search.naver?query={food_name}+칼로리"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    print(f"\n--- [Naver Scraping Log] ---")
    print(f"Searching: {food_name}")

    try:
        response = requests.get(search_url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 네이버 영양정보 박스의 칼로리 텍스트 추출 (보통 '단위_정보' 클래스 등에 위치)
            # 네이버 검색 UI가 변경될 수 있으므로 여러 선택자를 시도합니다.
            kcal_text = ""
            
            # 1. 지식백과나 영양정보 상단 노출 케이스
            target = soup.select_one(".api_txt_lines.cs_common_module_info_content") or \
                     soup.select_one(".n_info .n_kcal") or \
                     soup.select_one(".item_list dt:contains('칼로리') + dd")

            if target:
                kcal_text = target.get_text()
            else:
                # 2. 전체 텍스트에서 '숫자 + kcal' 패턴 찾기 (정규표현식)
                body_text = soup.get_text()
                match = re.search(r'(\d+)kcal', body_text)
                if match:
                    kcal_text = match.group(1)

            if kcal_text:
                # 숫자만 추출
                calories = int(re.sub(r'[^0-9]', '', kcal_text))
                print(f"Result -> {calories} kcal 찾음")
                return calories
                
        print("결과를 찾지 못했습니다.")
    except Exception as e:
        print(f"크롤링 중 오류: {e}")
    
    print(f"---------------------------\n")
    return 0

# 중복된 @app.route('/') 가 있다면 하나를 지우고 아래 내용으로 합치세요.
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        food_name = request.form.get('food_name')
        if food_name:
            # 네이버 크롤링 혹은 API 함수 호출
            calories = get_calories_from_naver(food_name)
            
            new_meal = Meal(food_name=food_name, calories=calories)
            db.session.add(new_meal)
            db.session.commit()
        return redirect(url_for('index'))

    # 전체 식단 내역 조회
    meals = Meal.query.order_by(Meal.date_posted.desc()).all()

    # 날짜별 총 칼로리 계산
    daily_stats = db.session.query(
        cast(Meal.date_posted, Date).label('date'),
        func.sum(Meal.calories).label('total_kcal')
    ).group_by(cast(Meal.date_posted, Date)).order_by(cast(Meal.date_posted, Date).desc()).all()

    return render_template('index.html', meals=meals, daily_stats=daily_stats)

@app.route('/delete/<int:id>')
def delete_meal(id):
    meal = Meal.query.get_or_404(id)
    db.session.delete(meal)
    db.session.commit()
    return redirect(url_for('index'))


if __name__ == "__main__":
    app.run(debug=True)