"""Tragaperras FALSA para probar el flujo Playwright -> visión sin tocar betsson.es ni dinero real.

Página exterior con el saldo "Betsson" en la cabecera y un iframe con un canvas que dibuja rodillos,
HUD (CRÉDITO / APUESTA / GANANCIA en formato español) y un botón Spin. Clic en Spin:
- con saldo: descuenta 1,00 €, gira 1,5 s y paga 5,00 €; la cabecera se actualiza con retraso.
- sin saldo: muestra "Saldo insuficiente" y no gira.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

BASE = "http://fake.test"
SIZE = (800, 450)
# Regiones en píxeles del canvas (se normalizan para la calibración).
REGIONS = {
    "spin_search": [620, 330, 180, 120],
    "reels": [100, 40, 600, 270],
    "balance": [10, 368, 210, 42],
    "wager": [230, 368, 170, 42],
    "payout": [410, 368, 180, 42],
    "currency": [10, 416, 80, 28],
    "message": [150, 90, 500, 180],
}
SPIN_BOX = [665, 345, 90, 90]   # recorte del botón para la plantilla


def money(value: str) -> str:
    return f"{float(value):.2f}".replace(".", ",") + " €"


def outer_html(balance: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0;font-family:Arial;background:#f4f4f4">
<header style="height:64px;display:flex;align-items:center;justify-content:flex-end;padding:0 24px;background:#fff">
<button id="saldo" style="font:bold 22px Arial;padding:8px 16px;background:#fff;border:2px solid #333;color:#111">Saldo {money(balance)}</button>
</header>
<iframe id="game" src="{BASE}/game.html?balance={balance}" width="{SIZE[0]}" height="{SIZE[1]}"
 style="border:0;display:block;margin:16px 40px"></iframe>
<script>addEventListener('message', e => document.getElementById('saldo').textContent = 'Saldo ' + e.data);</script>
</body></html>"""


GAME_HTML = """<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0;background:#0b1a2e">
<canvas id="c" width="800" height="450"></canvas>
<script>
const params = new URLSearchParams(location.search);
let balance = Math.round(parseFloat(params.get('balance')) * 100);
const bet = 100, win = 500;
let state = 'ready', payout = null, message = false, offset = 0, seed = 7;
const c = document.getElementById('c'), ctx = c.getContext('2d');
const palette = ['#e6194b','#3cb44b','#ffe119','#4363d8','#f58231','#911eb4','#46f0f0'];
const money = cents => (cents / 100).toFixed(2).replace('.', ',') + ' €';
const rand = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const post = () => parent.postMessage(money(balance), '*');
function draw() {
  ctx.fillStyle = '#0b1a2e'; ctx.fillRect(0, 0, 800, 450);
  for (let col = 0; col < 5; col++) for (let row = 0; row < 3; row++) {
    ctx.fillStyle = state === 'spinning' ? `hsl(${Math.floor(rand() * 360)},80%,55%)` : palette[(col * 3 + row + offset) % 7];
    ctx.fillRect(100 + col * 120 + 4, 40 + row * 90 + 4, 112, 82);
  }
  if (message) {
    ctx.fillStyle = '#5a0f12'; ctx.fillRect(150, 90, 500, 180);
    ctx.fillStyle = '#fff'; ctx.font = 'bold 34px Arial'; ctx.fillText('Saldo insuficiente', 185, 165);
    ctx.font = '22px Arial'; ctx.fillText('Recarga tu cuenta para seguir jugando', 185, 215);
  }
  ctx.fillStyle = '#000'; ctx.fillRect(0, 330, 800, 120);
  ctx.fillStyle = '#aaa'; ctx.font = '16px Arial';
  ctx.fillText('CRÉDITO', 20, 355); ctx.fillText('APUESTA', 240, 355); ctx.fillText('GANANCIA', 420, 355);
  ctx.fillStyle = '#fff'; ctx.font = 'bold 30px Arial';
  ctx.fillText(money(balance), 20, 400); ctx.fillText(money(bet), 240, 400);
  if (payout !== null) ctx.fillText(money(payout), 420, 400);
  ctx.font = 'bold 18px Arial'; ctx.fillText('EUR', 20, 437);
  if (state === 'ready') {
    ctx.fillStyle = '#1e9e3a'; ctx.beginPath(); ctx.arc(710, 390, 45, 0, 2 * Math.PI); ctx.fill();
    ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.moveTo(695, 365); ctx.lineTo(735, 390); ctx.lineTo(695, 415); ctx.fill();
    ctx.fillStyle = '#ffe119'; ctx.font = 'bold 12px Arial'; ctx.fillText('SPIN', 694, 432);
  } else {
    ctx.fillStyle = '#555'; ctx.fillRect(670, 350, 80, 80);
    ctx.fillStyle = '#ddd'; ctx.font = 'bold 18px Arial'; ctx.fillText('STOP', 686, 396);
  }
  requestAnimationFrame(draw);
}
c.addEventListener('click', e => {
  if (state !== 'ready' || Math.hypot(e.offsetX - 710, e.offsetY - 390) > 45) return;
  if (balance < bet) { message = true; return; }
  balance -= bet; payout = null; post(); state = 'spinning';
  setTimeout(() => { state = 'ready'; offset = 3; payout = win; balance += win; setTimeout(post, 400); }, 1500);
});
draw();
</script></body></html>"""


HTML = "text/html; charset=utf-8"


def handle_route(route) -> None:
    """Sirve el juego falso y bloquea cualquier otra petición (nunca se sale a internet)."""
    url = urlparse(route.request.url)
    if url.netloc != urlparse(BASE).netloc:
        route.abort()
    elif url.path.endswith("game.html"):
        route.fulfill(body=GAME_HTML, content_type=HTML)
    else:
        balance = parse_qs(url.query).get("balance", ["10.00"])[0]
        route.fulfill(body=outer_html(balance), content_type=HTML)
