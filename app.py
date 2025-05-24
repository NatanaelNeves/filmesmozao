# app.py (COMPLETO E FINAL)
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import hashlib # Para hash de senhas
import os # Para gerar a chave secreta (ex: os.urandom(24).hex())
import requests # Para fazer requisições HTTP para a API externa (OMDb)
from sqlalchemy import func # Importar func para funções de agregação (AVG, COUNT)

app = Flask(__name__)

# --- Configuração da Aplicação ---
# ATENÇÃO: PARA PRODUÇÃO NO RENDER, VOCÊ DEVE DEFINIR ESTAS VARIÁVEIS DE AMBIENTE.
# Para desenvolvimento local, 'fallback_secret_key_dev' e 'f9692cb3' serão usados.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'SUA_CHAVE_SECRETA_MUITO_FORTE_AQUI') # MUDAR! Gerar com os.urandom(24).hex()
OMDB_API_KEY = os.environ.get('OMDB_API_KEY', 'f9692cb3') # Mantenha sua chave de desenvolvimento local

# --- Configuração do banco de dados PostgreSQL (para Render) ou SQLite (para desenvolvimento local) ---
# A variável de ambiente DATABASE_URL será fornecida pelo Render.
# Para desenvolvimento local, ele usará sqlite:///movies.db.
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///movies.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Configuração do Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Define a rota para a página de login caso o usuário não esteja logado

# --- Modelos do Banco de Dados ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False) # Armazena o hash da senha

    def __repr__(self):
        return f'<User {self.username}>'

    def check_password(self, password):
        return hashlib.sha256(password.encode('utf-8')).hexdigest() == self.password_hash

class Movie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    director = db.Column(db.String(100), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    genre = db.Column(db.String(50), nullable=False)
    rating = db.Column(db.Float, nullable=True) # AGORA É OPCIONAL (nullable=True)
    watched_date = db.Column(db.Date, nullable=True) # Data assistida agora é opcional também
    comments = db.Column(db.Text)
    watched_by = db.Column(db.String(100), nullable=True) # Quem assistiu agora é opcional
    status = db.Column(db.String(20), nullable=False, default='assistido') # 'assistido' ou 'para_ver'

    plot = db.Column(db.Text)
    poster = db.Column(db.String(200))
    imdbID = db.Column(db.String(20), unique=True, nullable=True) # Campo para armazenar o IMDb ID

    def __repr__(self):
        return f'<Movie {self.title}>'

# --- Funções de Ajuda ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

def get_movie_data_from_omdb(title=None, year=None, imdb_id=None):
    params = {'apikey': OMDB_API_KEY}
    
    if imdb_id:
        params['i'] = imdb_id
    elif title:
        params['t'] = title
        if year:
            params['y'] = year
    else:
        return None

    params['type'] = 'movie'
    response = requests.get('http://www.omdbapi.com/', params=params)
    data = response.json()

    if data.get('Response') == 'False' and not imdb_id:
        params['type'] = 'series'
        response = requests.get('http://www.omdbapi.com/', params=params)
        data = response.json()

    if data.get('Response') == 'True':
        year_value = None
        if data.get('Year'):
            try:
                year_value = int(data.get('Year').split('–')[0])
            except ValueError:
                year_value = None

        return {
            'title': data.get('Title'),
            'director': data.get('Director'),
            'year': year_value,
            'genre': data.get('Genre'),
            'plot': data.get('Plot') if data.get('Plot') != 'N/A' else '',
            'poster': data.get('Poster') if data.get('Poster') != 'N/A' else url_for('static', filename='images/placeholder.png'),
            'imdbID': data.get('imdbID')
        }
    return None

# --- Inicialização do Banco de Dados e Usuários Padrão ---
with app.app_context():
    db.create_all()

    # Adiciona usuários iniciais (se não existirem)
    password_hash_voce = os.environ.get('PASSWORD_HASH_VOCE', hashlib.sha256("senha_dev_voce".encode('utf-8')).hexdigest())
    if not User.query.filter_by(username='voce').first():
        new_user = User(username='voce', password_hash=password_hash_voce)
        db.session.add(new_user)
        db.session.commit()
        print("Usuário 'voce' criado.")

    password_hash_namorada = os.environ.get('PASSWORD_HASH_NAMORADA', hashlib.sha256("senha_dev_namorada".encode('utf-8')).hexdigest())
    if not User.query.filter_by(username='namorada').first():
        new_user = User(username='namorada', password_hash=password_hash_namorada)
        db.session.add(new_user)
        db.session.commit()
        print("Usuário 'namorada' criado.")

# --- Rotas da Aplicação ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            flash('Login bem-sucedido!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha inválidos.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    query = Movie.query

    filter_year = request.args.get('filter_year')
    if filter_year and filter_year.isdigit():
        query = query.filter_by(year=int(filter_year))

    filter_genre = request.args.get('filter_genre')
    if filter_genre and filter_genre != 'all':
        query = query.filter_by(genre=filter_genre)

    filter_status = request.args.get('filter_status')
    if filter_status and filter_status != 'all':
        query = query.filter_by(status=filter_status)

    sort_by = request.args.get('sort_by', 'watched_date')
    order = request.args.get('order', 'desc')

    if sort_by == 'title':
        if order == 'asc':
            query = query.order_by(Movie.title.asc())
        else:
            query = query.order_by(Movie.title.desc())
    elif sort_by == 'rating':
        if order == 'asc':
            query = query.order_by(Movie.rating.asc().nulls_last())
        else:
            query = query.order_by(Movie.rating.desc().nulls_last())
    else: # watched_date (padrão)
        if order == 'asc':
            query = query.order_by(Movie.watched_date.asc())
        else:
            query = query.order_by(Movie.watched_date.desc())

    movies = query.all()
    
    genres = db.session.query(Movie.genre).distinct().all()
    genres = sorted([g[0] for g in genres if g[0]]) # Filter out None or empty string genres
    
    movie_statuses = ['assistido', 'para_ver']

    return render_template('index.html', movies=movies,
                           current_filter_year=filter_year,
                           current_filter_genre=filter_genre,
                           current_filter_status=filter_status,
                           current_sort_by=sort_by,
                           current_order=order,
                           genres=genres,
                           movie_statuses=movie_statuses)

@app.route('/search_omdb', methods=['GET'])
@login_required
def search_omdb():
    title = request.args.get('title')
    year = request.args.get('year')
    if not title:
        return jsonify({'error': 'Título é obrigatório para busca'}), 400

    params = {'s': title, 'apikey': OMDB_API_KEY}
    if year:
        params['y'] = year

    print(f"DEBUG: Buscando na OMDb com título='{title}', ano='{year}', params={params}")

    try:
        response = requests.get('http://www.omdbapi.com/', params=params)
        response.raise_for_status()
        data = response.json()
        print(f"DEBUG: Resposta JSON da OMDb: {data}")

        results = []
        if data.get('Response') == 'True' and data.get('Search'):
            for item in data['Search']:
                year_value = item.get('Year').split('–')[0] if item.get('Year') else ''
                results.append({
                    'title': item.get('Title'),
                    'year': year_value,
                    'imdbID': item.get('imdbID'),
                    'poster': item.get('Poster') if item.get('Poster') != 'N/A' else url_for('static', filename='images/placeholder.png'),
                    'type': item.get('Type')
                })
        else:
            error_message = data.get('Error', 'Erro desconhecido da OMDb API.')
            print(f"DEBUG: OMDb API retornou erro: {error_message}")
            
        return jsonify({'results': results})

    except requests.exceptions.RequestException as e:
        print(f"DEBUG: Erro de requisição HTTP para OMDb: {e}")
        return jsonify({'error': 'Erro ao conectar à OMDb API.'}), 500
    except ValueError as e:
        print(f"DEBUG: Erro ao decodificar JSON da OMDb: {e} - Resposta: {response.text}")
        return jsonify({'error': 'Resposta inválida da OMDb API.'}), 500

@app.route('/get_omdb_details/<imdb_id>', methods=['GET'])
@login_required
def get_omdb_details_route(imdb_id):
    movie_details = get_movie_data_from_omdb(imdb_id=imdb_id)
    if movie_details:
        return jsonify(movie_details)
    return jsonify({'error': 'Filme não encontrado na OMDb ou erro na API.'}), 404

@app.route('/add_movie', methods=['GET', 'POST'])
@login_required
def add_movie():
    if request.method == 'POST':
        imdb_id = request.form.get('imdb_id')
        
        title = request.form.get('title')
        director = request.form.get('director')
        year = request.form.get('year')
        genre = request.form.get('genre')
        plot = request.form.get('plot', '')
        poster = request.form.get('poster', url_for('static', filename='images/placeholder.png'))

        if imdb_id:
            api_data = get_movie_data_from_omdb(imdb_id=imdb_id)
            if api_data:
                title = api_data['title']
                director = api_data['director']
                year = api_data['year']
                genre = api_data['genre']
                plot = api_data['plot']
                poster = api_data['poster']
                imdb_id = api_data['imdbID']
            else:
                flash('Não foi possível obter os detalhes completos do filme da OMDb. Por favor, preencha manualmente.', 'warning')
        
        try:
            year = int(year) if year else None
        except ValueError:
            year = None

        rating_str = request.form.get('rating')
        rating = None
        if rating_str:
            try:
                rating = float(rating_str)
                if not (0.0 <= rating <= 10.0):
                    flash('Nota inválida. Por favor, insira um número entre 0.0 e 10.0.', 'danger')
                    return render_template('add_movie.html', movie_data={
                        'title': title, 'director': director, 'year': year, 'genre': genre,
                        'rating': rating_str, 'watched_date': request.form.get('watched_date'), 'comments': request.form.get('comments', ''),
                        'watched_by': request.form.get('watched_by'), 'plot': plot, 'poster': poster, 'imdbID': imdb_id,
                        'status': request.form.get('status')
                    })
            except ValueError:
                flash('Nota inválida. Por favor, insira um número válido ou deixe em branco.', 'danger')
                return render_template('add_movie.html', movie_data={
                    'title': title, 'director': director, 'year': year, 'genre': genre,
                    'rating': rating_str, 'watched_date': request.form.get('watched_date'), 'comments': request.form.get('comments', ''),
                    'watched_by': request.form.get('watched_by'), 'plot': plot, 'poster': poster, 'imdbID': imdb_id,
                    'status': request.form.get('status')
                })

        watched_date_str = request.form.get('watched_date')
        comments = request.form.get('comments', '')
        watched_by = request.form.get('watched_by')
        status = request.form.get('status', 'assistido')

        # Ajuste na validação: watched_date e watched_by só são obrigatórios se status for 'assistido'
        if status == 'assistido' and (not watched_date_str or not watched_by):
            flash('Para filmes "Assistidos", a Data e Quem Assistiu são obrigatórios.', 'danger')
            return render_template('add_movie.html', movie_data={
                'title': title, 'director': director, 'year': year, 'genre': genre,
                'rating': rating_str, 'watched_date': watched_date_str, 'comments': comments,
                'watched_by': watched_by, 'plot': plot, 'poster': poster, 'imdbID': imdb_id,
                'status': status
            })
        
        # Campos principais obrigatórios (independentemente do status)
        if not title or not director or not year or not genre:
            flash('Por favor, preencha Título, Diretor, Ano e Gênero.', 'danger')
            return render_template('add_movie.html', movie_data={
                'title': title, 'director': director, 'year': year, 'genre': genre,
                'rating': rating_str, 'watched_date': watched_date_str, 'comments': comments,
                'watched_by': watched_by, 'plot': plot, 'poster': poster, 'imdbID': imdb_id,
                'status': status
            })

        watched_date = None
        if watched_date_str:
            try:
                watched_date = datetime.strptime(watched_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Formato de data inválido. Use AAAA-MM-DD.', 'danger')
                return render_template('add_movie.html', movie_data={
                    'title': title, 'director': director, 'year': year, 'genre': genre,
                    'rating': rating_str, 'watched_date': watched_date_str, 'comments': comments,
                    'watched_by': watched_by, 'plot': plot, 'poster': poster, 'imdbID': imdb_id,
                    'status': status
                })

        new_movie = Movie(
            title=title,
            director=director,
            year=year,
            genre=genre,
            rating=rating,
            watched_date=watched_date,
            comments=comments,
            watched_by=watched_by,
            plot=plot,
            poster=poster,
            imdbID=imdb_id,
            status=status
        )
        db.session.add(new_movie)
        db.session.commit()
        flash('Filme adicionado com sucesso!', 'success')
        return redirect(url_for('index'))
    
    return render_template('add_movie.html', movie_data={})

@app.route('/edit_movie/<int:movie_id>', methods=['GET', 'POST'])
@login_required
def edit_movie(movie_id):
    movie = Movie.query.get_or_404(movie_id)

    if request.method == 'POST':
        movie.title = request.form['title']
        movie.director = request.form['director']
        movie.year = int(request.form['year'])
        movie.genre = request.form['genre']
        
        rating_str = request.form.get('rating')
        if rating_str:
            try:
                movie.rating = float(rating_str)
                if not (0.0 <= movie.rating <= 10.0):
                    flash('Nota inválida. Por favor, insira um número entre 0.0 e 10.0.', 'danger')
                    return render_template('edit_movie.html', movie=movie)
            except ValueError:
                flash('Nota inválida. Por favor, insira um número válido ou deixe em branco.', 'danger')
                return render_template('edit_movie.html', movie=movie)
        else:
            movie.rating = None

        watched_date_str = request.form.get('watched_date') # Use .get()
        comments = request.form.get('comments', '')
        watched_by = request.form.get('watched_by') # Use .get()
        movie.plot = request.form.get('plot', '')
        movie.poster = request.form.get('poster', url_for('static', filename='images/placeholder.png'))
        movie.imdbID = request.form.get('imdb_id')
        movie.status = request.form.get('status', 'assistido')

        # Ajuste na validação para edição: watched_date e watched_by só obrigatórios se status for 'assistido'
        if movie.status == 'assistido' and (not watched_date_str or not watched_by):
            flash('Para filmes "Assistidos", a Data e Quem Assistiu são obrigatórios.', 'danger')
            return render_template('edit_movie.html', movie=movie)

        # Campos principais obrigatórios (independentemente do status)
        if not movie.title or not movie.director or not movie.year or not movie.genre:
            flash('Por favor, preencha Título, Diretor, Ano e Gênero.', 'danger')
            return render_template('edit_movie.html', movie=movie)

        movie.watched_date = None # Resetar para evitar problemas se o status mudar para 'para_ver'
        if watched_date_str:
            try:
                movie.watched_date = datetime.strptime(watched_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Formato de data inválido. Use AAAA-MM-DD.', 'danger')
                return render_template('edit_movie.html', movie=movie)

        db.session.commit()
        flash('Filme atualizado com sucesso!', 'success')
        return redirect(url_for('index'))
    
    return render_template('edit_movie.html', movie=movie)

@app.route('/delete_movie/<int:movie_id>', methods=['POST'])
@login_required
def delete_movie(movie_id):
    movie = Movie.query.get_or_404(movie_id)
    db.session.delete(movie)
    db.session.commit()
    flash('Filme deletado com sucesso!', 'info')
    return redirect(url_for('index'))

@app.route('/stats')
@login_required
def stats():
    total_movies = db.session.query(Movie).filter_by(status='assistido').count()
    total_to_watch = db.session.query(Movie).filter_by(status='para_ver').count()

    avg_rating_result = db.session.query(func.avg(Movie.rating))\
                               .filter(Movie.status=='assistido', Movie.rating.isnot(None))\
                               .scalar()
    avg_rating = round(avg_rating_result, 1) if avg_rating_result is not None else 0.0

    # Top 5 gêneros assistidos
    top_genres_raw = db.session.query(Movie.genre, func.count(Movie.genre))\
                           .filter(Movie.status=='assistido', Movie.genre.isnot(None), Movie.genre != '')\
                           .group_by(Movie.genre)\
                           .order_by(func.count(Movie.genre).desc())\
                           .limit(5).all()
    # CONVERSÃO AQUI: De lista de Row/tuplas para lista de listas (ou dicts)
    top_genres = [[genre, count] for genre, count in top_genres_raw]


    # Filmes assistidos por cada usuário
    movies_by_user_raw = db.session.query(Movie.watched_by, func.count(Movie.watched_by))\
                               .filter(Movie.status=='assistido', Movie.watched_by.isnot(None), Movie.watched_by != '')\
                               .group_by(Movie.watched_by)\
                               .order_by(func.count(Movie.watched_by).desc())\
                               .all()
    # CONVERSÃO AQUI: De lista de Row/tuplas para lista de listas (ou dicts)
    movies_by_user = [[user, count] for user, count in movies_by_user_raw]


    recent_movies = db.session.query(Movie)\
                              .filter_by(status='assistido')\
                              .order_by(Movie.watched_date.desc())\
                              .limit(5).all()

    return render_template('stats.html',
                           total_movies=total_movies,
                           total_to_watch=total_to_watch,
                           avg_rating=avg_rating,
                           top_genres=top_genres,       # Agora é uma lista de listas Python, serializável
                           movies_by_user=movies_by_user, # Agora é uma lista de listas Python, serializável
                           recent_movies=recent_movies)

if __name__ == '__main__':
    app.run(debug=True)