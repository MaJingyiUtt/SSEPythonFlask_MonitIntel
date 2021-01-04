import hashlib
import json
import os
import queue
import secrets
import sqlite3
from flask import flash, Flask, jsonify, redirect, render_template, request, Response, url_for
from datetime import datetime

app = Flask(__name__)

secret = secrets.token_urlsafe(32)
app.secret_key = secret


@app.route("/")
def index():
    return render_template("login.html")


@app.route("/admin")
def admin():
    return render_template("admin.html")


@app.route("/login", methods=["POST"])
def login():

   # Récupération des valeurs entrées sur le formlaire

    login_form = request.form
    identifiant = login_form["uname"]
    input_mdp = login_form["psw"]

    # Connexion à la base de données

    conn = sqlite3.connect("profils_utilisateurs.db")
    cur = conn.cursor()
    print("Connexion réussie à SQLite")

    # Récupération du hash_mdp dans la base de données à partir de l'identifiant

    cur.execute("SELECT hash_mdp FROM utilisateurs WHERE identifiant = ?", (identifiant,))
    res = cur.fetchall()

    # Si l'identifiant n'est pas dans la base de données

    if len(res) == 0:
        error = "Cet identifiant n'existe pas dans la base de données."
        return render_template("login.html", error=error)

    # Si l'identifiant est dans la base de données

    hash_mdp = res[0][0]
    print("Hash récupéré")

    # Fermeture de la base de données

    cur.close()
    conn.close()
    print("Connexion SQlite fermée")

    # Récupération du salt et calcul du hash avec le salt et le mdp entré apr l'utilisateur

    salt = hash_mdp[:32]
    key = hashlib.pbkdf2_hmac("sha256", input_mdp.encode("utf-8"), salt, 100000, dklen=128)

    # Si le mot de passe est incorrect

    if hash_mdp[32:] != key:
        error = "Le mot de passe est incorrect."
        return render_template("login.html", error=error)

    return "Site en cours de construction..."


@app.route("/add_user", methods=["POST"])
def add_user():
    '''Fonction pour ajouter un utilisateur dans la base de données'''

    # Récupération des valeurs entrées sur le formulaire

    user_form = request.form
    identifiant = user_form["uname"]
    entreprise = user_form["entreprise"]
    sec_dep = user_form["section"]
    poste = user_form["poste"]

    # Création du hash du mot de passe et du salt associé

    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac("sha256", user_form["psw"].encode("utf-8"), salt, 100000, dklen=128)
    hash_mdp = salt + key

    # Connexion à la base de données

    conn = sqlite3.connect("profils_utilisateurs.db")
    cur = conn.cursor()
    print("Connexion réussie à SQLite")

    # Création de la table utilisateurs si elle n'existe pas

    cur.execute('''CREATE TABLE IF NOT EXISTS utilisateurs
                (identifiant TEXT PRIMARY KEY,
                hash_mdp TEXT,
                entreprise TEXT,
                section_departement TEXT,
                poste_tenu TEXT)''')

    # Insertion d'un nouvel utilisateur dans la base de données

    cur.execute(
        """INSERT INTO utilisateurs
                (identifiant, hash_mdp, entreprise, section_departement, poste_tenu) VALUES (?, ?, ?, ?, ?)""",
        (identifiant, hash_mdp, entreprise, sec_dep, poste)
    )

    # Fermeture de la base de données

    cur.close()
    conn.commit()
    print("Utilisateur inséré avec succès")
    conn.close()
    print("Connexion SQlite fermée")

    return render_template("admin.html")


@app.route("/add_device", methods=["POST"])
def add_device():
    '''Fonction pour ajouter un appareil dans la base de données'''

    # Récupération des valeurs entrées sur le formulaire

    device_form = request.form
    entreprise = device_form["entreprise"]
    sec_dep = device_form["section"]
    appareil = device_form["appareil"]
    variable = device_form["variable"]

    # Connexion à la base de données

    conn = sqlite3.connect("profils_utilisateurs.db")
    cur = conn.cursor()
    print("Connexion réussie à SQLite")

    # Création de la table appareils si elle n'existe pas

    cur.execute('''CREATE TABLE IF NOT EXISTS appareils
                (entreprise TEXT,
                section_departement TEXT,
                appareil TEXT PRIMARY KEY,
                variable_mesuree TEXT)''')

    # Insertion d'un nouvel appareil dans la base de données

    cur.execute(
        """INSERT INTO appareils
                (entreprise, section_departement, appareil, variable_mesuree) VALUES (?, ?, ?, ?)""",
        (entreprise, sec_dep, appareil, variable)
    )

    # Fermeture de la base de données

    cur.close()
    conn.commit()
    print("Appareil inséré avec succès")
    conn.close()
    print("Connexion SQlite fermée")

    return render_template("admin.html")


class MessageAnnouncer:
    def __init__(self):
        self.listeners = []

    def listen(self):
        q = queue.Queue(maxsize=5)
        self.listeners.append(q)
        return q

    def announce(self, msg):
        for i in reversed(range(len(self.listeners))):
            try:
                self.listeners[i].put_nowait(msg)
            except queue.Full:
                del self.listeners[i]


announcer = MessageAnnouncer()

# event: Jackson 5\\ndata: {"abc": 123}\\n\\n


def format_sse(data: str, event=None) -> str:
    msg = f"data: {data}\n\n"
    if event is not None:
        msg = f"event: {event}\n{msg}"
    return msg


@app.route("/input_data/<input_data>", methods=['GET'])
def get_values(input_data):
    input_data = str(input_data)
    input_var_elem = input_data.rsplit(".", 1)
    var = input_var_elem[0]
    if len(input_var_elem) > 1:
        extension = input_data.rsplit(".", 1)[1].lower()
        if extension not in {"csv", "tsv"}:
            return {"La ressource n'est pas au bon format"}, 200
        filename = input_data
        with open(filename, "r") as file:
            lines = file.readlines()
            if len(lines) <= 2:
                data = lines[1].split()[2]
            header = lines[0]
            mesured_var = header.split()[1]
            # 			print(mesured_var)
            filestart_time = datetime.strptime(
                " ".join(lines[1].split()[:2]), "%Y-%m-%d %H:%M:%S.%f"
            )
            fileend_time = datetime.strptime(
                " ".join(lines[-1].split()[:2]), "%Y-%m-%d %H:%M:%S.%f"
            )
            if fileend_time < filestart_time:
                data = lines[-1].split()[2]
                lines = lines[:-1]
            elif fileend_time > filestart_time:
                data = lines[1].split()[2]
                lines = [header] + lines[2:]
        file = open(filename, "w")
        file.write("".join(lines)[:-1])
        file.close()
        msg = format_sse(data=data)
        announcer.announce(msg=msg)
    return jsonify({"Status": "On progress..."}), 200


@app.route("/listen", methods=["GET"])
def listen():
    def stream():
        messages = announcer.listen()  # returns a queue.Queue
        while True:
            msg = messages.get()  # blocks until a new message arrives
            yield msg

    return Response(stream(), mimetype="text/event-stream")