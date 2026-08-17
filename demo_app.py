from flask import Flask
app = Flask(__name__)

@app.route("/")
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Demo App</title></head>
    <body style="font-family:sans-serif;background:#0a0a0a;color:#fff;display:flex;justify-content:center;align-items:center;height:100vh;margin:0">
      <div style="text-align:center">
        <h1 style="font-size:48px;margin-bottom:10px">&#10003;</h1>
        <h2 style="color:#22c55e">Tunnel is Working!</h2>
        <p style="color:#888;margin-top:10px">This demo app is running on port 4000</p>
        <p style="color:#555;margin-top:20px;font-size:12px">cloudflared &rarr; your-subdomain.yourdomain.com</p>
      </div>
    </body>
    </html>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4000)
