from flask import Flask, jsonify

app = Flask(__name__)

# routes
@app.route("/")
def home():
    return jsonify({"message": "secure devsecops app running"})

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# main
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
