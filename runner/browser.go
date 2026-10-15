package main

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/playwright-community/playwright-go"
)

// Importe en formato español con euro, p. ej. "1.234,56 €" o "€12,00".
// Betsson separa el importe y el símbolo con un espacio no separable (U+00A0), que \s no incluye en Go.
var EURO_AMOUNT = regexp.MustCompile(`(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})[\s\x{00a0}]*€|€[\s\x{00a0}]*(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})`)

// session agrupa el navegador y la página de un caso. Go es el único que controla Playwright.
type session struct {
	pw      *playwright.Playwright
	browser playwright.Browser
	page    playwright.Page
	config  market_config
}

// Sin vídeo: grabaría la pantalla de login. La evidencia son capturas del rectángulo del juego.
func open_session(config market_config, headed bool) (*session, error) {
	pw, err := playwright.Run()
	if err != nil {
		return nil, fmt.Errorf("no arranca Playwright: %w", err)
	}
	// Sin la marca de automatización: el WAF de Betsson bloquea el login (403) si el navegador se declara
	// automatizado. Mismo ajuste que usa la rama playwright_vision; autorizado por el equipo.
	browser, err := pw.Chromium.Launch(playwright.BrowserTypeLaunchOptions{
		Headless:          playwright.Bool(!headed),
		Args:              []string{"--disable-blink-features=AutomationControlled"},
		IgnoreDefaultArgs: []string{"--enable-automation"},
	})
	if err != nil {
		return nil, err
	}
	// Viewport fijo: la calibración de Pragmatic Play se midió con 1280x720.
	context, err := browser.NewContext(playwright.BrowserNewContextOptions{
		Locale:     playwright.String("es-ES"),
		TimezoneId: playwright.String("Europe/Madrid"),
		Viewport:   &playwright.Size{Width: 1280, Height: 720},
		// Capturas al doble de resolución: los importes del HUD miden ~11 px de alto a escala 1.
		DeviceScaleFactor: playwright.Float(2),
	})
	if err != nil {
		return nil, err
	}
	context.SetDefaultTimeout(20000)
	page, err := context.NewPage()
	if err != nil {
		return nil, err
	}
	return &session{pw: pw, browser: browser, page: page, config: config}, nil
}

func (s *session) close() {
	s.browser.Close()
	s.pw.Stop()
}

// dismiss_cookies acepta las cookies: con todas rechazadas Betsson puede impedir el login.
func (s *session) dismiss_cookies() {
	accept := s.page.GetByRole("button", playwright.PageGetByRoleOptions{Name: "Aceptar todas las cookies"})
	accept.Click(playwright.LocatorClickOptions{Timeout: playwright.Float(6000)})
}

// Cadenas largas (tokens, identificadores) que no deben acabar en un registro de diagnóstico.
var SECRET_LIKE = regexp.MustCompile(`[A-Za-z0-9_\-\.]{24,}`)

// log_network registra estado y error de las peticiones del sitio, solo si VALIDATOR_DEBUG_DIR está definida.
func (s *session) log_network() {
	dir := os.Getenv("VALIDATOR_DEBUG_DIR")
	if dir == "" {
		return
	}
	file, err := os.Create(filepath.Join(dir, "network.log"))
	if err != nil {
		return
	}
	var mutex sync.Mutex
	write := func(line string) {
		mutex.Lock()
		defer mutex.Unlock()
		fmt.Fprintln(file, line)
	}
	s.page.OnResponse(func(response playwright.Response) {
		request := response.Request()
		kind := request.ResourceType()
		if kind != "xhr" && kind != "fetch" && kind != "document" {
			return
		}
		method, status := request.Method(), response.Status()
		line := fmt.Sprintf("%s %d %s", method, status, strings.SplitN(response.URL(), "?", 2)[0])
		if method == "GET" && status < 400 {
			write(line)
			return
		}
		// Leer el cuerpo dentro del evento bloquea a playwright-go: se hace en otra goroutine.
		go func() {
			defer func() { recover() }()
			if body, err := response.Body(); err == nil {
				text := string(body)
				if len(text) > 400 {
					text = text[:400]
				}
				line += " | " + SECRET_LIKE.ReplaceAllString(text, "<oculto>")
			}
			write(line)
		}()
	})
	s.page.OnConsole(func(message playwright.ConsoleMessage) {
		if message.Type() == "error" {
			write("console: " + SECRET_LIKE.ReplaceAllString(message.Text(), "<oculto>"))
		}
	})
}

// login no captura pantallas: la pantalla de autenticación no forma parte de la evidencia.
func (s *session) login(user, password string) error {
	s.log_network()
	if _, err := s.page.Goto(s.config.BaseURL, playwright.PageGotoOptions{Timeout: playwright.Float(45000)}); err != nil {
		return fmt.Errorf("no abre el lobby: %w", err)
	}
	s.dismiss_cookies()
	open_button := s.page.GetByRole("button", playwright.PageGetByRoleOptions{Name: "Iniciar sesión", Exact: playwright.Bool(true)}).First()
	if err := open_button.Click(); err != nil {
		return fmt.Errorf("no aparece el botón de inicio de sesión: %w", err)
	}
	if err := s.page.GetByLabel("Usuario/email").Fill(user); err != nil {
		return fmt.Errorf("no aparece el campo de usuario: %w", err)
	}
	if err := s.page.GetByLabel("Contraseña", playwright.PageGetByLabelOptions{Exact: playwright.Bool(true)}).Fill(password); err != nil {
		return fmt.Errorf("no aparece el campo de contraseña: %w", err)
	}
	submit := s.page.GetByRole("button", playwright.PageGetByRoleOptions{Name: "Iniciar sesión", Exact: playwright.Bool(true)}).Last()
	if err := submit.Click(); err != nil {
		return fmt.Errorf("no se pudo enviar el login: %w", err)
	}
	// La sesión se da por iniciada cuando la cabecera muestra un saldo en euros.
	deadline := time.Now().Add(30 * time.Second)
	for time.Now().Before(deadline) {
		s.skip_passkey_offer()
		if _, _, err := s.betsson_balance(); err == nil {
			s.skip_passkey_offer()
			return nil
		}
		// Betsson muestra este aviso cuando rechaza temporalmente el acceso: no tiene sentido seguir esperando.
		rejected := s.page.GetByText("vuelve a intentarlo en breve")
		if visible, _ := rejected.IsVisible(); visible {
			s.debug_shot("login_rejected")
			return fmt.Errorf("Betsson rechazó el login temporalmente: «Actualiza la página y vuelve a intentarlo en breve»")
		}
		time.Sleep(time.Second)
	}
	s.debug_shot("login_failed")
	return fmt.Errorf("no se confirmó el inicio de sesión (sin saldo visible en la cabecera)")
}

// betsson_balance lee el saldo de la web exterior (DOM de Betsson, no del juego). Devuelve céntimos y texto.
func (s *session) betsson_balance() (int64, string, error) {
	// El importe va en un <span data-cs-mask> del botón de usuario (solo en el lobby; en la página del juego
	// la cabecera muestra «Saldo» sin importe). Selector confirmado por la rama playwright_vision.
	spans, err := s.page.Locator("span[data-cs-mask]").All()
	if err != nil {
		return 0, "", err
	}
	found := [][]string{}
	for _, span := range spans {
		text, err := span.InnerText(playwright.LocatorInnerTextOptions{Timeout: playwright.Float(1000)})
		if err != nil {
			continue
		}
		if match := EURO_AMOUNT.FindStringSubmatch(text); match != nil && strings.TrimSpace(match[0]) == strings.TrimSpace(text) {
			found = append(found, match)
		}
	}
	if len(found) != 1 {
		return 0, "", fmt.Errorf("se esperaba un único saldo en euros en la cabecera y hay %d", len(found))
	}
	cents, err := parse_spanish_euros(found[0])
	return cents, strings.TrimSpace(found[0][0]), err
}

// skip_passkey_offer cierra el aviso «Activar la clave de acceso» sin crear nunca la clave.
func (s *session) skip_passkey_offer() {
	if visible, _ := s.page.GetByText("Activar la clave de acceso").IsVisible(); visible {
		s.page.GetByRole("button", playwright.PageGetByRoleOptions{Name: "Cancelar", Exact: playwright.Bool(true)}).Click(
			playwright.LocatorClickOptions{Timeout: playwright.Float(3000)})
	}
}

// PREGAME_SCREENS son pantallas que Betsson muestra antes del juego (regulación española y avisos).
// Selectores confirmados por la rama playwright_vision con Bubble Up (Pragmatic Play), 2026-10-15.
var PREGAME_SCREENS = []struct {
	name   string
	detect string
	steps  []string
}{
	{"límites de sesión", `[data-test-id="session-settings"]`, []string{
		`[data-test-id="session-settings_time-limit-option-3600"]`,   // 1 hora
		`[data-test-id="session-settings_spending-limit-option-25"]`, // 25 % del saldo
		`[data-test-id="session-settings_submit-button-btn-1"]`,
	}},
	{"aviso de sesión de juego reciente", `[data-test-id="start-new-session-buttons-btn-2"]`, []string{
		`[data-test-id="start-new-session-buttons-btn-2"]`,
	}},
	{"panel de torneos", `text="Cerrar y no volver a mostrar"`, []string{
		`text="Cerrar y no volver a mostrar"`,
	}},
}

// handle_pregame resuelve una pantalla previa por pasada hasta que no queda ninguna.
func (s *session) handle_pregame() []string {
	handled := []string{}
	for pass := 0; pass < 6; pass++ {
		resolved := false
		for _, screen := range PREGAME_SCREENS {
			if visible, _ := s.page.Locator(screen.detect).First().IsVisible(); !visible {
				continue
			}
			for _, step := range screen.steps {
				s.page.Locator(step).First().Click(playwright.LocatorClickOptions{Timeout: playwright.Float(5000)})
				time.Sleep(500 * time.Millisecond)
			}
			handled = append(handled, screen.name)
			resolved = true
			break
		}
		if !resolved {
			return handled
		}
		time.Sleep(2 * time.Second)
	}
	return handled
}

func parse_spanish_euros(match []string) (int64, error) {
	integer_part, decimal_part := match[1], match[2]
	if integer_part == "" {
		integer_part, decimal_part = match[3], match[4]
	}
	euros, err := strconv.ParseInt(strings.ReplaceAll(integer_part, ".", ""), 10, 64)
	if err != nil {
		return 0, err
	}
	cents, err := strconv.ParseInt(decimal_part, 10, 64)
	return euros*100 + cents, err
}

// stable_betsson_balance repite la lectura hasta que dos lecturas seguidas coinciden.
func (s *session) stable_betsson_balance(wait time.Duration) (int64, string, error) {
	time.Sleep(wait)
	previous, _, err := s.betsson_balance()
	if err != nil {
		return 0, "", err
	}
	for attempt := 0; attempt < 5; attempt++ {
		time.Sleep(2 * time.Second)
		current, text, err := s.betsson_balance()
		if err != nil {
			return 0, "", err
		}
		if current == previous {
			return current, text, nil
		}
		previous = current
	}
	return 0, "", fmt.Errorf("el saldo Betsson no se estabilizó")
}

// open_game abre el juego en Real Play y devuelve el rectángulo visible del iframe en la página.
func (s *session) open_game() (playwright.Rect, error) {
	if _, err := s.page.Goto(s.config.BaseURL + s.config.GamePath); err != nil {
		return playwright.Rect{}, fmt.Errorf("no abre la página del juego: %w", err)
	}
	if visible, _ := s.page.GetByRole("button", playwright.PageGetByRoleOptions{Name: "Ingresar y jugar"}).IsVisible(); visible {
		return playwright.Rect{}, fmt.Errorf("el juego pide iniciar sesión: la sesión no se conservó")
	}
	time.Sleep(3 * time.Second)
	if handled := s.handle_pregame(); len(handled) > 0 {
		fmt.Println("   pantallas previas resueltas:", strings.Join(handled, ", "))
	}
	// La página tiene varios iframes: el juego es el visible más grande.
	deadline := time.Now().Add(45 * time.Second)
	for time.Now().Before(deadline) {
		// Las pantallas previas pueden aparecer en cascada y con retraso: se atienden también mientras se espera.
		if handled := s.handle_pregame(); len(handled) > 0 {
			fmt.Println("   pantallas previas resueltas:", strings.Join(handled, ", "))
		}
		iframes, _ := s.page.Locator("iframe").All()
		var best *playwright.Rect
		best_src := ""
		for _, iframe := range iframes {
			box, err := iframe.BoundingBox()
			if err != nil || box == nil || box.Width < 400 || box.Height < 300 {
				continue
			}
			if best == nil || box.Width*box.Height > best.Width*best.Height {
				best = box
				best_src, _ = iframe.GetAttribute("src")
			}
		}
		if best != nil {
			lower := strings.ToLower(best_src)
			if strings.Contains(lower, "demo") || strings.Contains(lower, "playmode=fun") {
				return playwright.Rect{}, fmt.Errorf("el juego parece estar en modo demo")
			}
			return *best, nil
		}
		time.Sleep(time.Second)
	}
	s.debug_shot("no_game_iframe")
	return playwright.Rect{}, fmt.Errorf("no aparece el iframe del juego")
}

// capture guarda solo el rectángulo del juego, para no incluir datos de la cuenta en la evidencia.
func (s *session) capture(rect playwright.Rect, path string) error {
	_, err := s.page.Screenshot(playwright.PageScreenshotOptions{
		Path: playwright.String(path),
		Clip: &playwright.Rect{X: rect.X, Y: rect.Y, Width: rect.Width, Height: rect.Height},
	})
	return err
}

// click_in_game convierte una posición relativa del juego (0-1) en coordenadas de la página.
func (s *session) click_in_game(rect playwright.Rect, point [2]float64) error {
	return s.page.Mouse().Click(rect.X+point[0]*rect.Width, rect.Y+point[1]*rect.Height)
}

// debug_shot guarda una captura de página completa solo si VALIDATOR_DEBUG_DIR está definida.
// Puede contener datos de la cuenta: nunca se guarda junto a las evidencias publicables.
func (s *session) debug_shot(name string) {
	dir := os.Getenv("VALIDATOR_DEBUG_DIR")
	if dir == "" {
		return
	}
	s.page.Screenshot(playwright.PageScreenshotOptions{Path: playwright.String(filepath.Join(dir, name+".png"))})
	dump := []string{}
	spans, _ := s.page.Locator("span[data-cs-mask]").All()
	for _, span := range spans {
		text, err := span.TextContent(playwright.LocatorTextContentOptions{Timeout: playwright.Float(1000)})
		dump = append(dump, fmt.Sprintf("span[data-cs-mask] %q %v", text, err))
	}
	os.WriteFile(filepath.Join(dir, name+".txt"), []byte(strings.Join(dump, "\n")), 0o600)
}
