import sqlite3
import datetime
import time
import calendar
import json
from datetime import timedelta
from calendar import timegm
from flask import Flask, request, session, redirect, url_for, g, render_template, abort, flash
from flask.ext.login import (LoginManager, current_user, redirect, login_required, login_user, logout_user, UserMixin, confirm_login)
from werkzeug.security import generate_password_hash, check_password_hash

# init things
app = Flask(__name__)

app.config.db = '/home/ubuntu/niko/db/niko.db'

# this... doesn't feel right
app.secret_key = 'hi'

# db communication setup
def connect_db():
  return sqlite3.connect(app.config.db)

@app.before_request
def before_request():
  g.db = connect_db()
  if current_user is not None:
    g.user = current_user

@app.teardown_request
def teardown_request(exception):
  g.db.close()

# flask-login init
login_manager = LoginManager()
login_manager.setup_app(app)

# constructors
class User(UserMixin):
  def __init__(self, username, email, password, team, id, register=False, active=True):
    self.username = username
    self.email = email
    self.password = password
    self.team = team
    self.id = id
    self.register = register
    if register:
      self._hash_password(password)
      self._set_id()

  def _hash_password(self, password):
    self.hashed_pw = generate_password_hash(str(password))

  def check_password(self, form_password):
    return check_password_hash(self.password, str(form_password))

  def _set_id(self):
    self.id = query_db('select id from users where username=?', (self.username,))

  def set_team(self, team_id):
    g.db.execute('update users set team = ? where id = ?', (team_id, self.id))
    g.db.commit()
    self.team = team_id

class Mood():
  def __init__(self, value, userid, username, entry_date, new=False):
    self.value = value
    self.userid = userid
    self.username = username
    self.entry_date = entry_date
    self.new = new
    if self.new:
      self._store_mood()

  def _store_mood(self):
    entry = query_db('insert into entries (mood, userid, username, entry_date) values (?, ?, ?, ?)', [self.value, self.userid, self.username, self.entry_date])
    g.db.commit()

# helpers

# dependency of flask-login
# does flask-login tear this down somewhere?
# get a nonetype, not callable error if I call it
@login_manager.user_loader
def load_user_by_id(id):
  return create_user_instance(id, 'id')

def load_user_by_name(username):
  return create_user_instance(username, 'username')

# for creating User objects for existing accounts
def create_user_instance(identifier, param_type):
  db_user = query_db('select username, email, password, team, id from users where (' + param_type + ' = ?)', (identifier,), one=True)
  if db_user:
    return User(db_user.get('username'), db_user.get('email'), db_user.get('password'), db_user.get('team'), db_user.get('id'))
  return None

# returns team id int
def create_team(team_name):
  cur = g.db.cursor()
  g.db.execute('insert into teams (name) values (?)', (team_name,))
  g.db.commit()
  team_id = cur.lastrowid
  cur.close()
  return team_id

# gives nice return value from db query
def query_db(query, args=(), one=False):
    cur = g.db.execute(query, args)
    rv = [dict((cur.description[idx][0], value)
               for idx, value in enumerate(row)) for row in cur.fetchall()]
    return (rv[0] if rv else None) if one else rv

# timespan = tuple(recent date, oldest date)
def get_moods(timespan):
  assert not isinstance(timespan, basestring)
  return query_db('select * from entries where entry_date > ? and entry_date < ? order by entry_date asc', (timespan[0], timespan[1]))

def get_team_name(team_id):
  return query_db('select name from teams where id = ?', (team_id,))

# returns monday of last week
def get_one_week_ago():
  today = datetime.datetime.now()
  return today - timedelta(days=today.weekday()) + timedelta(days=0, weeks=-1)

# returns friday of last week
def get_last_available_day():
  today = datetime.datetime.now()
  return today - timedelta(days=today.weekday()) + timedelta(days=4, weeks=-1)

# takes datetime obj
# returns unix timestamp
def get_unix_timestamp(date):
  return int(calendar.timegm(date.timetuple()))

# takes unix timestamp
# returns date object
def get_date(timestamp):
  return datetime.datetime.fromtimestamp(timestamp)

# returns unix timestamp 
def get_date_yesterday():
  return get_unix_timestamp(datetime.datetime.now() - timedelta(days=1))

# two datetime objs and a bool
def get_date_range(start_date, end_date, weekday=False):
  date_range = []
  for one_date in (start_date + datetime.timedelta(n) for n in range((end_date - start_date).days + 1)):
    date_range.append(get_pretty_date(one_date, weekday))
  return date_range

def get_pretty_date(date, day_of_week=False):
  string_format = '%A %m/%d/%Y' if day_of_week == True else '%m/%d/%Y'
  return date.strftime(string_format)

def get_entries_by_week():
  monday = get_one_week_ago()
  friday = get_last_available_day()
  return [get_moods((get_unix_timestamp(monday), get_unix_timestamp(friday))), get_date_range(monday, friday)] 

def get_entries_by_month(ref_date=get_last_available_day()):
  last_day = datetime.datetime.combine(datetime.date(ref_date.year, ref_date.month+1, 1) - datetime.timedelta(1,0,0), datetime.time(23, 59, 59))
  if last_day.month == datetime.datetime.now().month:
    last_day = ref_date

  first_day = datetime.datetime.combine(datetime.date(ref_date.year, ref_date.month, 1) + datetime.timedelta(0), datetime.time(0))
  return [get_moods((get_unix_timestamp(first_day), get_unix_timestamp(last_day))), get_date_range(first_day, last_day, True)]

def get_team_list():
  return query_db('select id, name from teams')

chart_request_params = {
  1: get_entries_by_week,
  2: get_entries_by_month
}

chart_time_map = {
  1: 'week',
  2: 'month'
}

log_reply_message = {
  1: "Oh no! Your entry is logged. Please go find a sympathetic ear. Or a hug",
  2: "Ok, got your entry. Sorry that things aren't going well! Go find a pick-me-up.",
  3: "Alright, entry stored. Carry on with your meh self.",
  4: "Thanks, smiley! Your entry was recorded. Rock.",
  5: "Hey, sunshine! The database did a little dance recording this entry."
}

days_of_week = ['M', 'Tu', 'W', 'Th', 'F']

# oh man
def validate_register_form(form):
  if not form['username']:
    return 'Please choose a username'
  elif not form['email']:
    return 'Please fill in your email'
  elif not form['password'] or not form['pw2']:
    return 'Please set a password and retype to validate'
  elif form['password'] != form['pw2']:
    return "Whoops, passwords didn't match. Try again."
  if query_db('select id from users where username=?', (form['username'],)):
    return 'This username is already taken'
  return False

# yuck
def assemble_chart(period):
  moods = chart_request_params[int(period)]()  
  template_data = {}
  template_data['date_range'] = moods.pop()
  template_data['user_records'] = {}
  for record in moods[0]:
    mood = {get_pretty_date(get_date(record['entry_date']), day_of_week = True if int(period) > 1 else False): record['mood']}
    if template_data['user_records'].get(record['username']):
      template_data['user_records'][record['username']].append(mood)  
    else:
      template_data['user_records'][record['username']] = [mood]
  return template_data

# ROUTES
# index
@app.route('/')
def index():
  if g.user.is_authenticated():
    return redirect(url_for('dashboard'))
  return redirect(url_for('login_page'))

# login form
@app.route('/login', methods=['GET', 'POST'])
def login_page():
  if request.method == 'POST':
    g.user = load_user_by_name(request.form.get('username'))
    if g.user.check_password(request.form.get('password')):
      login_user(g.user, remember=True)
      return redirect(url_for('dashboard'))
    flash("Didn't work. Try again, please.")
    return render_template('login.html')
  return render_template('login.html') 

# logout
@app.route('/logout')
@login_required
def logout():
  logout_user()
  return redirect(url_for('index'))

# registration form
@app.route('/register', methods=['GET', 'POST'])
def register_user():
  if request.method == 'POST':
    validation_errors = validate_register_form(request.form)
    if not validation_errors:
      user = User(request.form['username'], request.form['email'], request.form['password'], '', '', register=True)
      g.db.execute('insert into users (username, email, password) values (?, ?, ?)', 
                [user.username, user.email, user.hashed_pw])
      g.db.commit()
      flash('Welcome!')
      return redirect(url_for('login_page'))
    flash(validation_errors)
    return render_template('create-user.html')
  return render_template('create-user.html')    

# user dashboard
@app.route('/dashboard')
@login_required
def dashboard():
  if not g.user.team:
    teams = get_team_list()
    return render_template('dashboard.html', user = g.user, teams = teams)
  team_name = get_team_name(g.user.team)[0]['name']
  return render_template('dashboard.html', user = g.user, team_name = team_name)

# change team association
@app.route('/changeteam')
@login_required
def change_team():
  return render_template('change-team.html', teams = get_team_list())
    
# associate user and team
@app.route('/jointeam', methods=['POST'])
@login_required
def join_team():
  if not request.form['team']:
    flash("Sorry, I didn't catch your team choice. Try again?")
    return redirect(url_for('dashboard'))
  
  if request.form['team'] == 'new':
    if not request.form['new-team-name']:
      flash("If you'd like to create a new team, please input a name for it")
      return redirect(url_for('dashboard'))
    team_id = create_team(request.form['new-team-name'])
  else:
    team_id = int(request.form['team'])
  g.user.set_team(team_id)
  flash("Sweet, got it. Welcome to the team!")
  return redirect(url_for('dashboard'))

# chart request
@app.route('/chart', methods=['POST'])
@login_required
def show_chart():
  if request.method == 'POST':
    return redirect(url_for('show_chart_' + chart_time_map[int(request.form['time_period'])]))
  return render_template('dashboard.html', user = g.user)

@app.route('/chart/week')
@login_required
def show_chart_week():
  return render_template('chart_week.html', chart = assemble_chart(1), weekdays = days_of_week)

@app.route('/chart/month')
@login_required
def show_chart_month():
  return render_template('chart_month.html', chart = assemble_chart(2), weekdays = days_of_week)

@app.route('/export')
@login_required
def export_data():
  # throw out a csv or something
  return

# record mood entry
@app.route('/log', methods=['POST'])
@login_required
def log_mood():
  if request.method == 'POST':
    if not request.form['mood']:
      flash('Please select a mood before submitting')
      return redirect(url_for('dashboard'))
    entry_date = get_unix_timestamp(datetime.datetime.now()) if request.form['entry_for'] == 'today' else get_date_yesterday()
    Mood(request.form['mood'], request.form['userid'], request.form['username'], entry_date, new=True) 
    flash(log_reply_message[int(request.form['mood'])])
    return redirect(url_for('dashboard'))

# potential future bot endpoint
@app.route('/nikobot', methods=['POST'])
def nikobot_log():
  return

if __name__ == '__main__':
  app.run(host='0.0.0.0', debug=True)
