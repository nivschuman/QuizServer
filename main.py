from flask import Flask, url_for, request, json, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import random


app = Flask(__name__)
app.secret_key = "alon"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///site.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
CORS(app)


db = SQLAlchemy(app)


def generate_pin(digits):
    pin = ""

    for k in range(digits):
        pin += str(random.randint(0, 9))

    return pin


def generate_session_key(chars):
    key = "None"

    while key == "None":
        key = ""
        for k in range(chars):
            key += chr(random.randint(32, 126))

    return key


class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    quizzes_done = db.Column(db.Integer, default=0)
    correct_answers = db.Column(db.Integer, default=0)

    # relationship with Quiz
    quizzes = db.relationship("Quiz", backref="author", lazy=True, cascade="all, delete-orphan")


class Quiz(db.Model):
    __tablename__ = "quiz"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), default=f"Quiz{id}")
    pin = db.Column(db.String(8), unique=True)
    published = db.Column(db.Boolean, default=False, nullable=False)

    # connection with user
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # relationship with ChoiceQuestion
    choice_questions = db.relationship("ChoiceQuestion", backref="author", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"{self.name}, pin={self.pin}"

    def get_json(self):
        my_json = {"id": self.id, "name": self.name, "pin": self.pin, "published": self.published, "choice_questions": []}

        for choice_question in self.choice_questions:
            my_json["choice_questions"].append(choice_question.get_json())

        return my_json


class ChoiceQuestion(db.Model):
    __tablename__ = "choice_question"

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer)
    question = db.Column(db.String(120))

    # connection to quiz
    quiz_id = db.Column(db.Integer, db.ForeignKey("quiz.id"), nullable=False)

    # relationship with choice
    choices = db.relationship("Choice", backref="author", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        string = f"Q{self.number}"
        string += f"\nquestion: {self.question}"

        for choice in self.choices:
            string += "\n" + choice.__repr__()

        return string

    def get_json(self):
        my_json = {"id": self.id, "number": self.number, "question": self.question, "choices": []}

        for choice in self.choices:
            my_json["choices"].append(choice.get_json())

        return my_json


class Choice(db.Model):
    __tablename__ = "choice"

    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(120))
    correct = db.Column(db.Boolean)

    # connection to question
    choice_question_id = db.Column(db.Integer, db.ForeignKey("choice_question.id"), nullable=False)

    def __repr__(self):
        return f"text={self.text}, correct={self.correct}"

    def get_json(self):
        return {"id": self.id, "text": self.text, "correct": self.correct}


# create a new user. Return true if created, false otherwise
@app.route("/user/signup", methods=["POST"])
def sign_up():
    response = request.get_json()

    username = response["username"]
    password = response["password"]  # todo encryption

    user = User.query.filter_by(username=username).first()

    if user is not None:
        return {"created", "false"}

    new_user = User(username=username, password=password)

    db.session.add(new_user)
    db.session.commit()

    return {"created": "true"}


@app.route("/user/login", methods=["GET"])
def login():
    data = json.loads(request.args.get("data"))
    username = data["username"]
    password = data["password"]

    user = User.query.filter_by(username=username, password=password).first()

    if user is None:
        return {"key": "None"}

    key = generate_session_key(8)

    session["key"] = user.id

    return {"key": key}


# create a new quiz. Returns the pin.
@app.route("/create/newQuiz", methods=["GET"])
def new_quiz():
    pin = generate_pin(8)
    while Quiz.query.filter_by(pin=pin).first() is not None:
        pin = generate_pin(8)

    quiz = Quiz(name="MyQuiz", pin=pin)

    db.session.add(quiz)
    db.session.commit()

    return {"pin": pin}


# get current state of quiz questions and update quiz accordingly.
@app.route("/create/postQuestions", methods=["POST"])
def post_questions():
    response = request.get_json()

    pin = response["pin"]
    quiz = Quiz.query.filter_by(pin=pin).first()

    if quiz is None or quiz.published:
        return {"posted": "false"}

    questions = response["questions"]

    quiz.name = response["name"]

    quiz.choice_questions = []

    for question in questions:
        if question["type"] == "ChoiceQuestion":
            number = question["number"]
            question_text = question["question"]

            question_db = ChoiceQuestion(number=number, question=question_text, quiz_id=quiz.id)
            db.session.add(question_db)
            db.session.commit()

            for choice in question["choices"]:
                text = choice["text"]
                correct = choice["correct"]

                choice_db = Choice(text=text, correct=correct, choice_question_id=question_db.id)
                db.session.add(choice_db)
                db.session.commit()

    return {"posted": "true"}


# publish quiz of certain pin, allowing others to play it.
@app.route("/create/publishQuiz", methods=["POST"])
def publish_quiz():
    response = request.get_json()

    pin = response["pin"]
    quiz = Quiz.query.filter_by(pin=pin).first()

    if quiz is None:
        return {"published": "false"}

    quiz.published = True
    db.session.commit()

    return {"published": "true"}


# get pin of quiz and return whether a quiz with that pin exists and was published
@app.route("/enterPin/quizExists", methods=["GET"])
def quiz_exists():
    data = json.loads(request.args.get("data"))
    pin = data["pin"]

    quiz = Quiz.query.filter_by(pin=pin).first()

    if (quiz is None) or (not quiz.published):
        return {"exists": "false", "pin": pin}

    return {"exists": "true", "pin": pin}


# get pin and return a published quiz with that pin
@app.route("/play/getQuiz", methods=["POST"])
def get_quiz():
    data = json.loads(request.args.get("data"))
    pin = data["pin"]

    quiz = Quiz.query.filter_by(pin=pin).first()

    if (quiz is None) or (not quiz.published):
        return {"exists": "false", "pin": pin}

    return quiz.get_json()


if __name__ == "__main__":
    app.run()
    db.create_all()
