import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from gvc_bot.config import Config


HTML = """<!doctype html><html><head><title>Local appointment fixture</title></head><body>
<h1>Local appointment fixture — not GVC</h1>
<section id="availability" data-loaded="true">
<button class="slot" data-id="wrong-centre" data-date="2030-01-05" data-time="09:00" data-centre="Other" data-category="Tourism">Other centre</button>
<button class="slot" data-id="later" data-date="2030-01-20" data-time="10:30" data-centre="Demo centre" data-category="Tourism">20 January</button>
<button class="slot" data-id="earlier" data-date="2030-01-10" data-time="09:30" data-centre="Demo centre" data-category="Tourism">10 January</button>
</section>
<section id="review" hidden>
<span id="review-id"></span><span id="review-date"></span><span id="review-time"></span>
<span id="review-centre"></span><span id="review-category"></span>
<button id="submit">Confirm booking</button></section>
<section id="confirmation" hidden>Booked: <span id="reference"></span></section>
<script>
const mode = new URLSearchParams(location.search).get('mode');
const availability = document.querySelector('#availability');
window.selections = 0;
if (mode === 'empty') availability.innerHTML = '<p id="empty">No appointments</p>';
if (mode === 'changed') availability.innerHTML = '<p>Unexpected markup</p>';
if (mode === 'challenge') document.body.insertAdjacentHTML('afterbegin', '<p id="challenge">Verify you are human</p>');
if (mode === 'login') document.body.insertAdjacentHTML('afterbegin', '<form id="login">Login required</form>');
if (mode === 'invalid-date') document.querySelector('.slot').dataset.date = 'not-a-date';
if (mode === 'duplicate') document.querySelector('.slot').dataset.id = 'earlier';
for (const button of document.querySelectorAll('.slot')) button.onclick = () => {
  window.selections++;
  for (const key of ['id','date','time','centre','category']) document.querySelector('#review-' + key).textContent = button.dataset[key];
  if (mode === 'mismatch') document.querySelector('#review-centre').textContent = 'Wrong centre';
  document.querySelector('#review').hidden = false;
};
document.querySelector('#submit').onclick = async () => {
  const response = await fetch('/book', {method:'POST'});
  if (mode === 'lost-confirmation') return;
  const result = await response.json();
  document.querySelector('#reference').textContent = result.reference;
  document.querySelector('#confirmation').hidden = false;
};
</script></body></html>"""


@contextmanager
def fixture():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(429 if 'mode=rate-limit' in self.path else 200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML.encode())

        def do_POST(self):
            if self.path != '/book':
                self.send_error(404)
                return
            self.server.bookings += 1
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"reference":"LOCAL-DEMO-001"}')

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.bookings = 0
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f'http://127.0.0.1:{server.server_port}/'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def config_for(url, directory):
    path = Path(__file__).resolve().parents[1] / 'config.example.json'
    config = Config(**json.loads(path.read_text()))
    config.portal_url = url
    config.centre = 'Demo centre'
    config.category = 'Tourism'
    config.profile_dir = str(Path(directory) / 'profile')
    config.state_file = str(Path(directory) / 'booking.json')
    config.headless = True
    config.timeout_ms = 2500
    config.max_checks = 1
    return config.validate()
