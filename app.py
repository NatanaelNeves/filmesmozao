# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import hashlib # Para hash de senhas
import os # Para gerar a chave secreta (ex: os.urandom(24).hex())
import requests # Para fazer requisições HTTP para a API externa (OMDb)

app = Flask(__name__)

# --- Configuração da Aplicação ---
# ATENÇÃO: MUDE 'SUA_CHAVE_SECRETA_MUITO_FORTE_AQUI' PARA UMA CHAVE REALMENTE FORTE E ÚNICA!
# Exemplo de como gerar no terminal Python:
# import os
# print(os.urandom(24).hex())
app.config['SECRET_KEY'] = 'SUA_CHAVE_SECRETA_MUITO_FORTE_AQUI'

# Configuração do banco de dados SQLite
# O banco de dados será criado no mesmo diretório do app.py
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///movies.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Desativa o rastreamento de modificações para economizar memória

db = SQLAlchemy(app)

# --- Configuração do Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Define a rota para a página de login caso o usuário não esteja logado

# --- Chave da OMDb API ---
# COLOQUE A CHAVE DA OMDb API QUE VOCÊ PEGOU NO SITE http://www.omdbapi.com/ AQUI!
# Lembre-se que chaves de API devem ser mantidas em segredo em ambientes de produção,
# idealmente via variáveis de ambiente.
OMDB_API_KEY = 'f9692cb3'

# --- Modelos do Banco de Dados ---
# Estes modelos representam as tabelas no seu banco de dados

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False) # Armazena o hash da senha

    def __repr__(self):
        return f'<User {self.username}>'

    # Método para verificar a senha (usado no login)
    def check_password(self, password):
        # Em uma aplicação real, use uma biblioteca como Werkzeug.security.check_password_hash
        # para hashes mais seguros (ex: bcrypt). Hashlib é para demonstração simples.
        return hashlib.sha256(password.encode('utf-8')).hexdigest() == self.password_hash

class Movie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    director = db.Column(db.String(100), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    genre = db.Column(db.String(50), nullable=False)
    rating = db.Column(db.Float, nullable=False)
    watched_date = db.Column(db.Date, nullable=False) # Tipo Date para datas
    comments = db.Column(db.Text) # Campo de comentários, pode ser opcional
    watched_by = db.Column(db.String(100), nullable=False) # Quem adicionou/assistiu

    # NOVOS CAMPOS PARA DADOS DA OMDb API
    plot = db.Column(db.Text) # Sinopse
    poster = db.Column(db.String(200)) # URL do pôster

    def __repr__(self):
        return f'<Movie {self.title}>'

# --- Funções de Ajuda ---

# Função para carregar o usuário para o Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Context Processor para injetar a função 'now' em todos os templates (para o rodapé)
@app.context_processor
def inject_now():
    return {'now': datetime.now()} # Retorna a função datetime.now para ser chamada no template

# NOVA FUNÇÃO: Busca dados do filme na OMDb API
def get_movie_data_from_omdb(title=None, year=None, imdb_id=None):
    """
    Busca dados de filme/série na OMDb API.
    Pode buscar por título+ano ou por imdb_id.
    Retorna um dicionário com os dados relevantes ou None se não encontrar.
    """
    params = {'apikey': OMDB_API_KEY}
    
    if imdb_id:
        params['i'] = imdb_id # Busca por IMDb ID
    elif title:
        params['t'] = title # Busca por título exato
        if year:
            params['y'] = year # Adiciona o ano ao parâmetro de busca, se fornecido
    else:
        return None # Precisa de título ou imdb_id

    # Tenta buscar como 'movie' primeiro
    params['type'] = 'movie'
    response = requests.get('http://www.omdbapi.com/', params=params)
    data = response.json()

    # Se não encontrar como filme, tenta buscar como 'series'
    if data.get('Response') == 'False' and not imdb_id: # Se não for por IMDb ID e não achou como filme
        params['type'] = 'series'
        response = requests.get('http://www.omdbapi.com/', params=params)
        data = response.json()

    if data.get('Response') == 'True':
        # A OMDb API pode retornar o ano como "YYYY–YYYY" para séries ou "YYYY" para filmes.
        # Pegamos apenas o primeiro ano se for o caso.
        year_value = None
        if data.get('Year'):
            try:
                year_value = int(data.get('Year').split('–')[0])
            except ValueError:
                year_value = None # Se não conseguir converter, deixa como None

        return {
            'title': data.get('Title'),
            'director': data.get('Director'),
            'year': year_value,
            'genre': data.get('Genre'),
            'plot': data.get('Plot') if data.get('Plot') != 'N/A' else '',
            'poster': data.get('Poster') if data.get('Poster') != 'N/A' else url_for('static', filename='images/placeholder.png'),
            'imdbID': data.get('imdbID') # Inclui o IMDb ID para passar adiante, se necessário
        }
    return None

# --- Inicialização do Banco de Dados e Usuários Padrão ---
# Este bloco será executado uma vez quando o aplicativo iniciar.
# Ele cria as tabelas e adiciona usuários padrão se eles não existirem.
with app.app_context():
    db.create_all() # Cria todas as tabelas definidas pelos modelos (User e Movie)

    # Adiciona usuários iniciais (se não existirem)
    # ATENÇÃO: MUDE AS SENHAS PARA ALGO SEGURO!
    # Gere os hashes das senhas no terminal Python usando hashlib.sha256:
    # import hashlib
    # print(hashlib.sha256("sua_senha_para_voce".encode('utf-8')).hexdigest())
    # print(hashlib.sha256("sua_senha_para_namorada".encode('utf-8')).hexdigest())

    # Usuário 'voce'
    if not User.query.filter_by(username='voce').first():
        # COLOQUE O HASH DA SENHA PARA O USUÁRIO 'voce' AQUI
        password_hash_voce = "69b8d3dee5068ecc1fc97b540e664abd02364f9c383c4bc3ae43fa466e3be4cd" # MUDAR!
        new_user = User(username='voce', password_hash=password_hash_voce)
        db.session.add(new_user)
        db.session.commit()
        print("Usuário 'voce' criado.")

    # Usuário 'namorada'
    if not User.query.filter_by(username='namorada').first():
        # COLOQUE O HASH DA SENHA PARA O USUÁRIO 'namorada' AQUI
        password_hash_namorada = "69b8d3dee5068ecc1fc97b540e664abd02364f9c383c4bc3ae43fa466e3be4cd"  # MUDAR!
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

        # Verifica o hash da senha
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
    # Lógica de filtro e ordenação
    query = Movie.query

    # Filtro por ano
    filter_year = request.args.get('filter_year')
    if filter_year and filter_year.isdigit():
        query = query.filter_by(year=int(filter_year))

    # Filtro por gênero
    filter_genre = request.args.get('filter_genre')
    if filter_genre and filter_genre != 'all':
        query = query.filter_by(genre=filter_genre)

    # Ordenação
    sort_by = request.args.get('sort_by', 'watched_date') # Padrão: por data
    order = request.args.get('order', 'desc') # Padrão: descendente

    if sort_by == 'title':
        if order == 'asc':
            query = query.order_by(Movie.title.asc())
        else:
            query = query.order_by(Movie.title.desc())
    elif sort_by == 'rating':
        if order == 'asc':
            query = query.order_by(Movie.rating.asc())
        else:
            query = query.order_by(Movie.rating.desc())
    else: # watched_date
        if order == 'asc':
            query = query.order_by(Movie.watched_date.asc())
        else:
            query = query.order_by(Movie.watched_date.desc()) # Ordem padrão para data é mais recente primeiro

    movies = query.all()
    
    # Obter lista de gêneros únicos para o filtro
    genres = db.session.query(Movie.genre).distinct().all()
    genres = sorted([g[0] for g in genres])

    return render_template('index.html', movies=movies,
                           current_filter_year=filter_year,
                           current_filter_genre=filter_genre,
                           current_sort_by=sort_by,
                           current_order=order,
                           genres=genres)

# Rota para buscar filmes via API (AJAX) - Para preencher a caixa de sugestões
# Rota para buscar filmes via API (AJAX) - Para preencher a caixa de sugestões
@app.route('/search_omdb', methods=['GET'])
@login_required
def search_omdb():
    title = request.args.get('title')
    year = request.args.get('year')
    if not title:
        return jsonify({'error': 'Título é obrigatório para busca'}), 400

    params = {'s': title, 'apikey': OMDB_API_KEY} # 's' para busca geral (search)
    if year:
        params['y'] = year

    print(f"DEBUG: Buscando na OMDb com título='{title}', ano='{year}', params={params}") # DEBUG 1

    try:
        response = requests.get('http://www.omdbapi.com/', params=params)
        response.raise_for_status() # Lança um erro para status de erro HTTP (4xx ou 5xx)
        data = response.json()
        print(f"DEBUG: Resposta JSON da OMDb: {data}") # DEBUG 2

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
            # Se a resposta for False, 'Error' geralmente contém a mensagem da API
            error_message = data.get('Error', 'Erro desconhecido da OMDb API.')
            print(f"DEBUG: OMDb API retornou erro: {error_message}") # DEBUG 3
            # Podemos até retornar essa mensagem de erro para o frontend se quisermos.
            # Por enquanto, só vamos logar.
            
        return jsonify({'results': results})

    except requests.exceptions.RequestException as e:
        print(f"DEBUG: Erro de requisição HTTP para OMDb: {e}") # DEBUG 4
        return jsonify({'error': 'Erro ao conectar à OMDb API.'}), 500
    except ValueError as e: # Catch para erro de JSON (se a resposta não for JSON válida)
        print(f"DEBUG: Erro ao decodificar JSON da OMDb: {e} - Resposta: {response.text}") # DEBUG 5
        return jsonify({'error': 'Resposta inválida da OMDb API.'}), 500

# ...

# Rota para obter detalhes de um filme específico via IMDb ID (AJAX)
@app.route('/get_omdb_details/<imdb_id>', methods=['GET'])
@login_required
def get_omdb_details_route(imdb_id):
    # Reutiliza a função get_movie_data_from_omdb para obter os detalhes
    movie_details = get_movie_data_from_omdb(imdb_id=imdb_id)
    if movie_details:
        return jsonify(movie_details)
    return jsonify({'error': 'Filme não encontrado na OMDb ou erro na API.'}), 404


@app.route('/add_movie', methods=['GET', 'POST'])
@login_required
def add_movie():
    if request.method == 'POST':
        # Se veio da busca via API (com imdb_id)
        imdb_id = request.form.get('imdb_id')
        
        # Dados que serão preenchidos
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
            else:
                flash('Não foi possível obter os detalhes completos do filme da OMDb. Por favor, preencha manualmente.', 'warning')
        
        # Tenta converter o ano para int, se disponível
        try:
            year = int(year) if year else None
        except ValueError:
            year = None # Se não for um número válido

        # Campos obrigatórios que o usuário preenche
        rating = request.form['rating']
        watched_date_str = request.form['watched_date']
        comments = request.form.get('comments', '')
        watched_by = request.form['watched_by']

        # Validação de campos
        if not title or not director or not year or not genre or not rating or not watched_date_str:
            flash('Por favor, preencha todos os campos obrigatórios (Título, Diretor, Ano, Gênero, Nota, Data).', 'danger')
            # Renderiza o formulário novamente com os dados que o usuário já inseriu
            return render_template('add_movie.html', movie_data={
                'title': title, 'director': director, 'year': year, 'genre': genre,
                'rating': rating, 'watched_date': watched_date_str, 'comments': comments,
                'watched_by': watched_by, 'plot': plot, 'poster': poster, 'imdbID': imdb_id
            })

        try:
            rating = float(rating)
            if not (0.0 <= rating <= 10.0):
                raise ValueError("Nota deve estar entre 0.0 e 10.0.")
        except ValueError:
            flash('Nota inválida. Por favor, insira um número entre 0.0 e 10.0.', 'danger')
            return render_template('add_movie.html', movie_data={
                'title': title, 'director': director, 'year': year, 'genre': genre,
                'rating': rating, 'watched_date': watched_date_str, 'comments': comments,
                'watched_by': watched_by, 'plot': plot, 'poster': poster, 'imdbID': imdb_id
            })

        try:
            watched_date = datetime.strptime(watched_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Formato de data inválido. Use AAAA-MM-DD.', 'danger')
            return render_template('add_movie.html', movie_data={
                'title': title, 'director': director, 'year': year, 'genre': genre,
                'rating': rating, 'watched_date': watched_date_str, 'comments': comments,
                'watched_by': watched_by, 'plot': plot, 'poster': poster, 'imdbID': imdb_id
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
            poster=poster
        )
        db.session.add(new_movie)
        db.session.commit()
        flash('Filme adicionado com sucesso!', 'success')
        return redirect(url_for('index'))
    
    # Para requisição GET, renderiza o formulário vazio
    return render_template('add_movie.html')

@app.route('/edit_movie/<int:movie_id>', methods=['GET', 'POST'])
@login_required
def edit_movie(movie_id):
    movie = Movie.query.get_or_404(movie_id)

    if request.method == 'POST':
        movie.title = request.form['title']
        movie.director = request.form['director']
        movie.year = int(request.form['year'])
        movie.genre = request.form['genre']
        movie.rating = float(request.form['rating'])
        watched_date_str = request.form['watched_date']
        movie.comments = request.form.get('comments', '')
        movie.watched_by = request.form['watched_by']
        movie.plot = request.form.get('plot', '') # Permite editar a sinopse também
        movie.poster = request.form.get('poster', url_for('static', filename='images/placeholder.png')) # Permite editar o pôster

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

if __name__ == '__main__':
    app.run(debug=True)