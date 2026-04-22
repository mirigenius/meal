import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, cast, Date
from datetime import datetime, timedelta
import pytz
import re

app = Flask(__name__)

# [DB 설정]
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:postgres@localhost:5432/postgres'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# [기초대사량]
BMR = 1247

def get_kst_now():
    return datetime.now(pytz.timezone('Asia/Seoul'))

# --- [DB 모델] ---
class Meal(db.Model):
    __tablename__ = 'meal'
    id = db.Column(db.Integer, primary_key=True)
    food_name = db.Column(db.String(100), nullable=False)
    calories = db.Column(db.Integer, nullable=False)
    date_posted = db.Column(db.DateTime, default=get_kst_now)

class Exercise(db.Model):
    __tablename__ = 'exercise'
    id = db.Column(db.Integer, primary_key=True)
    ex_name = db.Column(db.String(100), nullable=False)
    ex_calories = db.Column(db.Integer, nullable=False)
    date_posted = db.Column(db.DateTime, default=get_kst_now)

# --- [크롤링 함수] ---
def get_cal_from_naver(name, is_exercise=False):
    suffix = "소모+칼로리" if is_exercise else "칼로리"
    search_url = f"https://search.naver.com/search.naver?query={name}+{suffix}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(search_url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        match = re.search(r'(\d+)kcal', soup.get_text())
        return int(match.group(1)) if match else 0
    except:
        return 0

# --- [메인 라우트] ---
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        if form_type == 'meal':
            name = request.form.get('food_name')
            db.session.add(Meal(food_name=name, calories=get_cal_from_naver(name)))
        elif form_type == 'exercise':
            name = request.form.get('ex_name')
            db.session.add(Exercise(ex_name=name, ex_calories=get_cal_from_naver(name, True)))
        db.session.commit()
        return redirect(url_for('index'))

    # --- [날짜 필터링 로직] ---
    kst_now = get_kst_now()
    default_to = kst_now.date()
    default_from = default_to - timedelta(days=6)

    from_str = request.args.get('from_date', default_from.strftime('%Y-%m-%d'))
    to_str = request.args.get('to_date', default_to.strftime('%Y-%m-%d'))

    from_date = datetime.strptime(from_str, '%Y-%m-%d').date()
    to_date = datetime.strptime(to_str, '%Y-%m-%d').date()

    # --- [DB 조회 (날짜 구간 적용)] ---
    m_stats = db.session.query(cast(Meal.date_posted, Date).label('d'), func.sum(Meal.calories).label('s'))\
                .filter(cast(Meal.date_posted, Date) >= from_date, cast(Meal.date_posted, Date) <= to_date)\
                .group_by(cast(Meal.date_posted, Date)).all()
                
    e_stats = db.session.query(cast(Exercise.date_posted, Date).label('d'), func.sum(Exercise.ex_calories).label('s'))\
                .filter(cast(Exercise.date_posted, Date) >= from_date, cast(Exercise.date_posted, Date) <= to_date)\
                .group_by(cast(Exercise.date_posted, Date)).all()

    m_all = Meal.query.filter(cast(Meal.date_posted, Date) >= from_date, cast(Meal.date_posted, Date) <= to_date).order_by(Meal.date_posted.desc()).all()
    e_all = Exercise.query.filter(cast(Exercise.date_posted, Date) >= from_date, cast(Exercise.date_posted, Date) <= to_date).order_by(Exercise.date_posted.desc()).all()

    # --- [통합 리포트 생성 (수정된 부분)] ---
    report = {}
    
    # 섭취 데이터가 있는 날짜만 딕셔너리에 추가/업데이트
    for d, s in m_stats: 
        date_str = d.strftime('%Y-%m-%d')
        report.setdefault(date_str, {'in': 0, 'out': 0, 'bmr': BMR})['in'] = s
        
    # 운동 데이터가 있는 날짜만 딕셔너리에 추가/업데이트
    for d, s in e_stats: 
        date_str = d.strftime('%Y-%m-%d')
        report.setdefault(date_str, {'in': 0, 'out': 0, 'bmr': BMR})['out'] = s

    sorted_report = sorted(report.items(), reverse=True)

    # --- [상세 내역 그룹화] ---
    g_meals = {}; g_exs = {}
    for m in m_all: g_meals.setdefault(m.date_posted.strftime('%Y-%m-%d'), []).append(m)
    for e in e_all: g_exs.setdefault(e.date_posted.strftime('%Y-%m-%d'), []).append(e)

    return render_template('index.html', 
                           m_stats=m_stats, e_stats=e_stats, 
                           g_meals=g_meals, g_exs=g_exs, 
                           summary=sorted_report, bmr=BMR,
                           from_date=from_str, to_date=to_str)

@app.route('/delete/<type>/<int:id>')
def delete_item(type, id):
    target = Meal.query.get(id) if type == 'meal' else Exercise.query.get(id)
    if target:
        db.session.delete(target)
        db.session.commit()
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run(port=5001, debug=True)