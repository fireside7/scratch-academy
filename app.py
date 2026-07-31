# import required modules
import base64
import json
import sqlite3
from openai import OpenAI
from flask import Flask, Response, abort, jsonify, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
import os
from database import (
    init_db,
    create_user,
    get_user_by_email,
    get_user_by_id,
    save_chat_message,
    get_chat_history,
    get_upload_for_message,
)

# load environment variables from dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# initialize flask app and set secret key
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "secret-key")

# setup the database
init_db()

# inject current user info into template context
@app.context_processor
def inject_user():
    user = None
    user_id = session.get('user_id')
    if user_id:
        user = get_user_by_id(user_id)
        if user:
            user = dict(user)
    return {'current_user': user}

# define list of available lessons
LESSONS = [
    {
        "id": 1,
        "title": "Meet Scratch!",
        "level": "Beginner",
        "blurb": "Introduction to the Scratch editor, sprites, and backdrops.",
    },
    {
        "id": 2,
        "title": "Basic Movement",
        "level": "Beginner",
        "blurb": "Use movement blocks to move, glide, and bounce around.",
    },
    {
        "id": 3,
        "title": "Loops",
        "level": "Beginner",
        "blurb": "Repeat actions from 3 times to forever using loops.",
    },
    {
        "id": 4,
        "title": "Events and Broadcasts",
        "level": "Intermediate",
        "blurb": "Make sprites react to clicks, key presses, and messages from each other.",
    },
    {
        "id": 5,
        "title": "Variables",
        "level": "Intermediate",
        "blurb": "Store numbers and words so your project can remember things.",
    },
    {
        "id": 6,
        "title": "If Statements and Logic",
        "level": "Intermediate",
        "blurb": "Implement logic in your programs.",
    },
    {
        "id": 7,
        "title": "Clones & Custom Blocks",
        "level": "Advanced",
        "blurb": "Make copies of sprites with their own behaviour and make new blocks.",
    },
    {
        "id": 8,
        "title": "Build a Complete Game",
        "level": "Advanced",
        "blurb": "Put everything together into a game.",
    },
]

# set constants for upload limits and chat settings
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # API limit headroom; keeps base64 payloads sane
MAX_HISTORY_TURNS = 20

# set system prompt for the ai helper
# The following prompt was generated with AI
SYSTEM_PROMPT = """You are the friendly AI coding helper on a Scratch tutorial website for kids and beginners.

Students upload screenshots of their Scratch block code when something isn't working. Your job:
1. Look carefully at the blocks in the screenshot.
2. Point out what is wrong (or confirm it looks correct).
3. Explain the fix in simple, encouraging language a beginner can follow, referring to blocks by their color and name (e.g. the yellow "when green flag clicked" block).
4. Keep answers short and focused — a few sentences or a short list, not an essay.

Never write text-based program code as the solution; describe which Scratch blocks to use and how to arrange them."""

# find a lesson by its id
def get_lesson(lesson_id):
    return next((l for l in LESSONS if l["id"] == lesson_id), None)


_client = None

# initialize and return openrouter client
def get_client():
    global _client
    if _client is None:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not set")
        _client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    return _client

# render home page with lesson list
@app.route("/")
def index():
    return render_template("index.html", lessons=LESSONS)

# render specific lesson page
@app.route("/lesson/<int:lesson_id>")
def lesson(lesson_id):
    lesson = get_lesson(lesson_id)
    if lesson is None:
        abort(404)
    return render_template("lesson.html", lesson=lesson)

# process chat input, screenshots, and generate ai responses
@app.post("/api/analyze")
def analyze():
    user_id = session.get('user_id')
    lesson = get_lesson(request.form.get("lesson_id", type=int) or 0)
    message = (request.form.get("message") or "").strip()

    # parse and filter chat history
    try:
        history = json.loads(request.form.get("history") or "[]")
        assert isinstance(history, list)
    except (ValueError, AssertionError):
        history = []
    history = [
        {"role": turn["role"], "content": turn["content"]}
        for turn in history[-MAX_HISTORY_TURNS:]
        if isinstance(turn, dict)
        and turn.get("role") in ("user", "assistant")
        and isinstance(turn.get("content"), str)
        and turn["content"].strip()
    ]

    content = []
    screenshot_data = None
    screenshot_mimetype = None
    screenshot = request.files.get("screenshot")
    has_screenshot = bool(screenshot and screenshot.filename)
    
    # process image upload if present
    if has_screenshot:
        if screenshot.mimetype not in ALLOWED_IMAGE_TYPES:
            return jsonify(error="Please upload a PNG, JPEG, GIF, or WebP image."), 400
        data = screenshot.read()
        if len(data) > MAX_IMAGE_BYTES:
            return jsonify(error="That image is too big — please upload one under 10 MB."), 400
        screenshot_data = data
        screenshot_mimetype = screenshot.mimetype
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": screenshot.mimetype,
                "data": base64.standard_b64encode(data).decode("utf-8"),
            },
        })

    # attach text prompt or default image message
    if message:
        content.append({"type": "text", "text": message})
    elif has_screenshot:
        content.append({
            "type": "text",
            "text": "Here's a screenshot of my Scratch code. Can you tell me what's wrong with it?",
        })

    # validate that input exists
    if not content:
        return jsonify(error="Type a question or upload a screenshot first."), 400

    # prepare system prompt
    system = SYSTEM_PROMPT
    if lesson:
        system += f"\n\nThe student is currently working through the lesson \"{lesson['title']}\" ({lesson['level']})."

    # fetch openrouter client
    try:
        client = get_client()
    except Exception:
        return jsonify(error=(
            "The AI helper isn't set up yet. Ask the site admin to set the "
            "OPENROUTER_API_KEY environment variable and restart the server."
        )), 503

    # send request to ai api
    try:
        messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": content}]
        response = client.chat.completions.create(
            model="openrouter/auto",
            max_tokens=16000,
            messages=messages,
        )
    except Exception as e:
        error_str = str(e).lower()
        if "authentication" in error_str or "unauthorized" in error_str or "invalid" in error_str:
            return jsonify(error="The AI helper's API key is invalid. Ask the site admin to check it."), 503
        elif "rate limit" in error_str or "429" in error_str:
            return jsonify(error="The AI helper is a bit overwhelmed right now — try again in a minute!"), 429
        elif "connection" in error_str or "timeout" in error_str:
            return jsonify(error="Couldn't reach the AI helper. Check your internet connection and try again."), 502
        else:
            return jsonify(error="Something went wrong talking to the AI helper. Please try again."), 502

    reply = response.choices[0].message.content

    # save chat message to database if user is logged in
    if user_id and lesson:
        save_chat_message(
            user_id=user_id,
            lesson_id=lesson.get("id"),
            user_message=message,
            assistant_reply=reply,
            screenshot_data=screenshot_data,
            screenshot_mimetype=screenshot_mimetype
        )

    return jsonify(reply=reply)

# handle user registration
@app.route("/sign-up", methods=['GET', 'POST'])
def sign_up():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        phone_number = request.form['phone_number']
        password = request.form['password']

        try:
            user_id = create_user(first_name, last_name, email, phone_number, generate_password_hash(password))
            session['user_id'] = user_id
            return redirect("/")
        except sqlite3.IntegrityError:
            return "Email already exists", 400
        except Exception as e:
            return f"Error creating account: {str(e)}", 400

    return render_template('sign_up.html')

# handle user login
@app.route("/log-in", methods=['GET', 'POST'])
def log_in():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = get_user_by_email(email)
        if not user:
            return "User not found", 400

        if check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            return redirect("/")
        else:
            return "Incorrect password", 400

    return render_template("log_in.html")

# log out current user
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# fetch chat history for a lesson
@app.get("/api/chat-history/<int:lesson_id>")
def get_lesson_chat_history(lesson_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify(error="Not logged in"), 401

    messages = get_chat_history(user_id, lesson_id=lesson_id, limit=100)
    history = []
    for msg in messages:
        history.append({
            "id": msg['id'],
            "user_message": msg['user_message'],
            "assistant_reply": msg['assistant_reply'],
            "has_screenshot": bool(msg['has_screenshot']),
            "created_at": msg['created_at']
        })
    return jsonify(history=history)

# serve uploaded image for a chat message
@app.get("/api/chat-upload/<int:message_id>")
def chat_upload(message_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify(error="Not logged in"), 401

    upload = get_upload_for_message(message_id, user_id)
    if not upload:
        abort(404)
    return Response(upload['data'], mimetype=upload['mimetype'])

# run server
if __name__ == "__main__":
    app.run(debug=True, port=int(os.getenv("PORT", "5000")))
