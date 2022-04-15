from flask import Flask, url_for, request, json, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import random
from passlib.hash import sha256_crypt


app = Flask(__name__)
app.secret_key = "alon"

app.config.from_object(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///site.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

CORS(app)


db = SQLAlchemy(app)


def generate_pin(digits):
    pin = ""

    for k in range(digits):
        pin += str(random.randint(0, 9))

    return pin


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

    # relationship with Status
    statuses = db.relationship("Status", backref="author", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"{self.name}, pin={self.pin}"

    def get_json(self, with_answers=False):
        my_json = {"name": self.name, "pin": self.pin, "published": self.published, "choice_questions": []}

        for choice_question in self.choice_questions:
            my_json["choice_questions"].append(choice_question.get_json(with_answers))

        return my_json

    def get_statuses_json(self):
        statuses_json = []

        for status in self.statuses:
            statuses_json.append(status.get_json())

        return statuses_json


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

    def get_json(self, with_answers=False):
        my_json = {"number": self.number, "question": self.question, "choices": []}

        for choice in self.choices:
            my_json["choices"].append(choice.get_json(with_answers))

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

    def get_json(self, with_answers=False):
        if not with_answers:
            return {"text": self.text}
        else:
            return {"text": self.text, "correct": self.correct}


class Status(db.Model):
    __tablename__ = "status"

    id = db.Column(db.Integer, primary_key=True)
    grade = db.Column(db.Integer)
    amount_played = db.Column(db.Integer, default=1)
    user_id = db.Column(db.Integer, nullable=False)

    # connection to quiz
    quiz_id = db.Column(db.Integer, db.ForeignKey("quiz.id"), nullable=False)

    def get_json(self):
        user = User.query.filter_by(id=self.user_id).first()
        return {"username": user.username, "grade": self.grade, "amount": self.amount_played}


# create a new user. Return true if created, false otherwise
@app.route("/user/signup", methods=["POST"])
def sign_up():
    response = request.get_json()

    username = response["username"]
    password = response["password"]

    hashed_password = sha256_crypt.encrypt(password)

    user = User.query.filter_by(username=username).first()

    if user is not None:
        return {"created": "false"}

    new_user = User(username=username, password=hashed_password)

    db.session.add(new_user)
    db.session.commit()

    return {"created": "true"}


# try to login. Return user id if able to login
@app.route("/user/login", methods=["GET"])
def login():
    data = json.loads(request.args.get("data"))
    username = data["username"]
    password = data["password"]

    user = User.query.filter_by(username=username).first()

    if user is None or not sha256_crypt.verify(password, user.password):
        return {"user_id": "None"}

    return {"user_id": user.id}


# get user id. Returns stats of user with this id
@app.route("/home/userinfo", methods=["GET"])
def user_info():
    user_id = json.loads(request.args.get("data"))

    user = User.query.filter_by(id=user_id).first()

    if user is None:
        return {"found": "false"}

    return_data = {"username": user.username,
                   "quizzes_done": user.quizzes_done,
                   "correct_answers": user.correct_answers,
                   "quizzes_made": len(user.quizzes),
                   "found": "true"
                   }

    return return_data


# create a new quiz for user with given id. Returns the pin.
@app.route("/create/newQuiz", methods=["GET"])
def new_quiz():
    user_id = json.loads(request.args.get("data"))
    pin = generate_pin(8)
    while Quiz.query.filter_by(pin=pin).first() is not None:
        pin = generate_pin(8)

    quiz = Quiz(name="MyQuiz", pin=pin, user_id=user_id)

    db.session.add(quiz)
    db.session.commit()

    return {"pin": pin}


# get current state of quiz questions and update quiz accordingly for user.
@app.route("/create/postQuestions", methods=["POST"])
def post_questions():
    response = request.get_json()["quiz"]
    user_id = request.get_json()["user_id"]

    pin = response["pin"]
    quiz = Quiz.query.filter_by(pin=pin, user_id=user_id).first()

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
    pin = request.get_json()["pin"]
    user_id = request.get_json()["user_id"]

    quiz = Quiz.query.filter_by(pin=pin, user_id=user_id).first()

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
@app.route("/play/getQuiz", methods=["GET"])
def get_quiz():
    data = json.loads(request.args.get("data"))

    pin = data["pin"]

    quiz = Quiz.query.filter_by(pin=pin).first()

    if (quiz is None) or (not quiz.published):
        return {"exists": "false", "pin": pin}

    return quiz.get_json()


# gets pin of quiz, user and what player answered. Returns number of questions he got right.
# also updates user stats accordingly
@app.route("/play/correctAnswers", methods=["POST"])
def correct_answers():
    response = request.get_json()["quiz"]
    user_id = request.get_json()["user_id"]

    pin = response["pin"]

    quiz = Quiz.query.filter_by(pin=pin).first()

    if (quiz is None) or (not quiz.published):
        return {"error": "cannot play quiz"}

    correct = 0

    # go over each question sent
    for question in response["questions"]:
        if question["type"] == "ChoiceQuestion":
            is_correct = True
            # find matching question in quiz
            number = question["number"]
            question_text = question["question"]
            quiz_question = ChoiceQuestion.query.filter_by(quiz_id=quiz.id, number=number, question=question_text).first()

            # go over each choice in question sent
            for choice in question["choices"]:
                # find matching choice in question
                text = choice["text"]

                question_choice = Choice.query.filter_by(text=text, choice_question_id=quiz_question.id).first()

                if choice["correct"] != question_choice.correct:
                    is_correct = False
                    break

            if is_correct:
                correct += 1

    user = User.query.filter_by(id=user_id).first()

    grade = (correct * 100) / len(quiz.choice_questions)

    # update user stats
    user.correct_answers += correct
    user.quizzes_done += 1

    # create new status
    status = Status.query.filter_by(user_id=user_id, quiz_id=quiz.id).first()

    if status is None:
        new_status = Status(grade=grade, user_id=user_id, quiz_id=quiz.id)
        db.session.add(new_status)
    else:
        status.amount_played += 1
        status.grade = max(grade, status.grade)

    db.session.commit()

    return {"correctAnswers": correct}


# gets quiz pin and returns all user statuses for that quiz
@app.route("/leaderboard/getStatuses", methods=["GET"])
def get_statuses():
    data = json.loads(request.args.get("data"))

    pin = data["pin"]

    quiz = Quiz.query.filter_by(published=True, pin=pin).first()

    if quiz is None:
        return {"found": "false"}

    return {"found": "true", "statuses": quiz.get_statuses_json()}


# get list of all quizzes this user has creates and not published
@app.route("/edit/getUserQuizzes", methods=["GET"])
def get_user_quizzes():
    data = json.loads(request.args.get("data"))

    user = User.query.filter_by(id=data).first()

    json_to_return = []

    for quiz in user.quizzes:
        json_to_return.append(quiz.get_json())

    return {"quizzes": json_to_return}


# get quiz with answers for user to edit
@app.route("/create/getQuizWithAnswers", methods=["GET"])
def get_quiz_with_answers():
    data = json.loads(request.args.get("data"))

    user_id = data["user_id"]
    pin = data["pin"]

    quiz = Quiz.query.filter_by(user_id=user_id, pin=pin, published=False).first()

    return {"quiz": quiz.get_json(True)}


# delete quiz of certain pin created by user
@app.route("/edit/deleteQuiz", methods=["GET"])
def delete_quiz():
    data = json.loads(request.args.get("data"))

    user_id = data["user_id"]
    pin = data["pin"]

    quiz = Quiz.query.filter_by(user_id=user_id, pin=pin, published=False).first()

    if quiz is not None:
        db.session.delete(quiz)
        db.session.commit()

        return {"deleted": "true", "pin": pin}

    return {"deleted": "false", "pin": pin}


if __name__ == "__main__":
    app.run()
    db.create_all()
