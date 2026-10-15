package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/playwright-community/playwright-go"
)

const (
	MOTION_STARTED = 0.05  // fracción de píxeles de los rodillos que cambian cuando giran
	MOTION_STILL   = 0.005 // por debajo, dos capturas seguidas se consideran iguales
	START_TIMEOUT  = 10 * time.Second
)

// game_run guarda lo necesario para capturar y analizar el juego de un caso.
type game_run struct {
	s        *session
	vision   *vision_client
	rect     playwright.Rect
	dir      string
	frame_id int
}

func (g *game_run) frame(label string) (string, error) {
	g.frame_id++
	path := filepath.Join(g.dir, fmt.Sprintf("%03d_%s.png", g.frame_id, label))
	return path, g.s.capture(g.rect, path)
}

func (g *game_run) find(path string, template template_config) (location, error) {
	return g.vision.locate(path, template.Path, template.ReferenceWidth, template.Threshold)
}

// enter_game pasa la pantalla de carga de Pragmatic (su botón no es una apuesta) hasta ver el botón de giro.
func (g *game_run) enter_game() error {
	deadline := time.Now().Add(60 * time.Second)
	for time.Now().Before(deadline) {
		time.Sleep(2 * time.Second)
		path, err := g.frame("loading")
		if err != nil {
			return err
		}
		if spin, err := g.find(path, g.s.config.SpinTemplate); err != nil {
			return err
		} else if spin.Found {
			return nil
		}
		splash, err := g.find(path, g.s.config.SplashTemplate)
		if err != nil {
			return err
		}
		if splash.Found {
			if err := g.s.click_in_game(g.rect, [2]float64{*splash.X, *splash.Y}); err != nil {
				return err
			}
			time.Sleep(3 * time.Second)
		}
	}
	return fmt.Errorf("el juego no llegó a mostrar el botón de giro")
}

// read_amounts lee saldo del juego y apuesta en dos capturas separadas; solo acepta importes que coinciden.
func (g *game_run) read_amounts(label string) (map[string]region_reading, []string, error) {
	regions := map[string][4]float64{
		"game_balance": g.s.config.Regions["game_balance"],
		"bet":          g.s.config.Regions["bet"],
	}
	paths := []string{}
	readings := []map[string]region_reading{}
	for i := 0; i < 2; i++ {
		if i > 0 {
			time.Sleep(time.Second)
		}
		path, err := g.frame(label)
		if err != nil {
			return nil, nil, err
		}
		reading, err := g.vision.read(path, regions, g.s.config.AmountTextHSV)
		if err != nil {
			return nil, nil, err
		}
		paths = append(paths, path)
		readings = append(readings, reading)
	}
	first, second := readings[0], readings[1]
	for name, reading := range first {
		other := second[name]
		if reading.Cents != nil && (other.Cents == nil || *reading.Cents != *other.Cents) {
			message := fmt.Sprintf("lecturas distintas entre capturas: %q / %q", reading.Text, other.Text)
			reading.Cents, reading.Error = nil, &message
			first[name] = reading
		}
	}
	return first, paths, nil
}

// read_win devuelve el premio observado. «¡HAGA SU APUESTA!» en la línea de premio es la señal calibrada
// de premio cero; si hay un importe, se lee en dos capturas que deben coincidir. Sin señal clara: desconocido.
func (g *game_run) read_win(label string) (region_reading, []string, error) {
	region := g.s.config.Regions["win"]
	paths := []string{}
	results := []region_reading{}
	for i := 0; i < 2; i++ {
		if i > 0 {
			time.Sleep(time.Second)
		}
		path, err := g.frame(label)
		if err != nil {
			return region_reading{}, nil, err
		}
		paths = append(paths, path)
		idle, match, err := g.vision.find_text(path, g.s.config.WinIdlePatterns, &region)
		if err != nil {
			return region_reading{}, nil, err
		}
		if idle {
			zero := int64(0)
			results = append(results, region_reading{Text: match, Cents: &zero, Confidence: 100})
			continue
		}
		readings, err := g.vision.read(path, map[string][4]float64{"win": region}, nil)
		if err != nil {
			return region_reading{}, nil, err
		}
		results = append(results, readings["win"])
	}
	first, second := results[0], results[1]
	if first.Cents == nil || second.Cents == nil || *first.Cents != *second.Cents {
		message := fmt.Sprintf("premio no legible o inestable: %q / %q", first.Text, second.Text)
		first.Cents, first.Error = nil, &message
	}
	return first, paths, nil
}

// click_spin localiza el botón de giro en una captura nueva y lo pulsa.
func (g *game_run) click_spin() (string, error) {
	path, err := g.frame("before_click")
	if err != nil {
		return "", err
	}
	spin, err := g.find(path, g.s.config.SpinTemplate)
	if err != nil {
		return path, err
	}
	if !spin.Found {
		return path, fmt.Errorf("no se localizó el botón de giro (puntuación %.2f)", spin.Score)
	}
	return path, g.s.click_in_game(g.rect, [2]float64{*spin.X, *spin.Y})
}

// watch_spin observa los rodillos tras el clic: primero exige movimiento y después reposo sostenido.
func (g *game_run) watch_spin() (started bool, ended bool, evidence []string, err error) {
	timing := g.s.config.Timing
	reels := g.s.config.Regions["reels"]
	previous, err := g.frame("after_click")
	if err != nil {
		return false, false, nil, err
	}
	evidence = append(evidence, previous)
	start_deadline := time.Now().Add(START_TIMEOUT)
	end_deadline := time.Now().Add(time.Duration(timing.SpinTimeoutS) * time.Second)
	still_frames := 0
	for time.Now().Before(end_deadline) {
		time.Sleep(time.Duration(timing.PollIntervalMs) * time.Millisecond)
		current, err := g.frame("spin")
		if err != nil {
			return started, false, evidence, err
		}
		changed, err := g.vision.motion(previous, current, reels)
		if err != nil {
			return started, false, evidence, err
		}
		previous = current
		if !started {
			if changed >= MOTION_STARTED {
				started = true
				evidence = append(evidence, current)
			} else if time.Now().After(start_deadline) {
				return false, false, append(evidence, current), nil
			}
			continue
		}
		if changed < MOTION_STILL {
			still_frames++
		} else {
			still_frames = 0
		}
		if still_frames >= timing.StillFramesToSettle {
			return true, true, append(evidence, current), nil
		}
	}
	return started, false, append(evidence, previous), nil
}

// outer_reels_changed mira solo las columnas exteriores de rodillos, que los avisos del juego no tapan.
func (g *game_run) outer_reels_changed(image_a, image_b string) bool {
	for _, name := range []string{"reels_left", "reels_right"} {
		changed, err := g.vision.motion(image_a, image_b, g.s.config.Regions[name])
		if err != nil || changed >= MOTION_STARTED {
			return true // sin poder medirlo no se afirma que no hubo giro
		}
	}
	return false
}

// open_and_enter abre el juego en Real Play y llega hasta la pantalla con el botón de giro.
func (g *game_run) open_and_enter() error {
	rect, err := g.s.open_game()
	if err != nil {
		return err
	}
	g.rect = rect
	return g.enter_game()
}

func cents_value(reading region_reading) (int64, bool) {
	if reading.Cents == nil {
		return 0, false
	}
	return *reading.Cents, true
}

func currency_check(before map[string]region_reading, betsson_text string, evidence []string) check {
	currency_ok := before["bet"].HasEuro && before["game_balance"].HasEuro
	return verdict("Moneda EUR en el juego y en Betsson", currency_ok, true,
		fmt.Sprintf("apuesta «%s», saldo juego «%s», saldo Betsson «%s»", before["bet"].Text, before["game_balance"].Text, strings.ReplaceAll(betsson_text, "\u00a0", " ")), evidence)
}

// run_completed_spin es el escenario T01: un giro pagado que empieza, termina y cuadra los saldos.
func run_completed_spin(s *session, vision *vision_client, dir string) []check {
	g := &game_run{s: s, vision: vision, dir: dir}
	betsson_before, betsson_before_text, err := s.stable_betsson_balance(0)
	if err != nil {
		return []check{error_check("Saldo Betsson antes", err)}
	}
	if err := g.open_and_enter(); err != nil {
		return []check{error_check("Abrir juego en Real Play", err)}
	}
	before, before_evidence, err := g.read_amounts("before")
	if err != nil {
		return []check{error_check("Lectura previa del juego", err)}
	}
	bet, bet_ok := cents_value(before["bet"])
	if !bet_ok {
		// Sin apuesta legible no se gira: el resultado no podría verificarse y gastaría dinero.
		return []check{
			check{"Apuesta visible antes del giro", INCONCLUSIVE, show(before["bet"]), before_evidence},
			currency_check(before, betsson_before_text, before_evidence),
		}
	}
	click_evidence, err := g.click_spin()
	if err != nil {
		return []check{error_check("Pulsar giro", err)}
	}
	started, ended, spin_evidence, err := g.watch_spin()
	if err != nil {
		return []check{error_check("Observar giro", err)}
	}
	spin_evidence = append([]string{click_evidence}, spin_evidence...)
	time.Sleep(2 * time.Second)
	win_reading, win_evidence, err := g.read_win("win")
	if err != nil {
		return []check{error_check("Lectura del premio", err)}
	}
	after, after_evidence, err := g.read_amounts("after")
	if err != nil {
		return []check{error_check("Lectura posterior del juego", err)}
	}

	checks := []check{}
	switch {
	case started && ended:
		checks = append(checks, check{"El giro empezó y terminó", PASS, "movimiento de rodillos tras el clic y después reposo sostenido", spin_evidence})
	case !started:
		checks = append(checks, check{"El giro empezó y terminó", FAIL, "no se observó movimiento de rodillos tras el clic", spin_evidence})
	default:
		checks = append(checks, check{"El giro empezó y terminó", INCONCLUSIVE, "los rodillos no llegaron a un reposo estable en el tiempo límite (¿bonus?)", spin_evidence})
	}
	checks = append(checks, currency_check(before, betsson_before_text, before_evidence))

	balance_before, balance_before_ok := cents_value(before["game_balance"])
	balance_after, balance_after_ok := cents_value(after["game_balance"])
	win, win_ok := cents_value(win_reading)
	checks = append(checks, verdict("Premio observado en pantalla", win_ok, true,
		fmt.Sprintf("línea de premio %q → %s", win_reading.Text, show(win_reading)), win_evidence))

	game_ok := balance_before_ok && balance_after_ok && win_ok && started && ended
	checks = append(checks, verdict("Saldo del juego = antes − apuesta + premio (la apuesta mostrada se aplicó)",
		balance_after == balance_before-bet+win, game_ok,
		fmt.Sprintf("juego antes %s, apuesta %s, premio %s, juego después %s",
			show(before["game_balance"]), show(before["bet"]), show(win_reading), show(after["game_balance"])),
		append(append([]string{}, before_evidence...), after_evidence...)))

	// Volver a la web de Betsson para leer el saldo exterior una vez liquidado el giro.
	s.page.Goto(s.config.BaseURL)
	betsson_after, betsson_after_text, err := s.stable_betsson_balance(time.Duration(s.config.Timing.BalanceWaitS) * time.Second)
	if err != nil {
		return append(checks, error_check("Saldo Betsson después", err))
	}
	checks = append(checks, verdict("Saldo Betsson = antes − apuesta + premio",
		betsson_after == betsson_before-bet+win, win_ok && started && ended,
		fmt.Sprintf("Betsson antes %s, después %s, apuesta %s, premio %s (esperado %s)",
			betsson_before_text, betsson_after_text, format_cents(bet), show(win_reading), format_cents(betsson_before-bet+win)), nil))
	return checks
}

// run_insufficient_balance es el escenario T02: el intento se rechaza con mensaje y sin mover saldos.
func run_insufficient_balance(s *session, vision *vision_client, dir string) []check {
	g := &game_run{s: s, vision: vision, dir: dir}
	betsson_before, betsson_before_text, err := s.stable_betsson_balance(0)
	if err != nil {
		return []check{error_check("Saldo Betsson antes", err)}
	}
	if err := g.open_and_enter(); err != nil {
		return []check{error_check("Abrir juego en Real Play", err)}
	}
	before, before_evidence, err := g.read_amounts("before")
	if err != nil {
		return []check{error_check("Lectura previa del juego", err)}
	}
	click_evidence, err := g.click_spin()
	if err != nil {
		return []check{error_check("Pulsar giro", err)}
	}

	// Durante unos segundos se busca el mensaje y se vigila que los rodillos no giren.
	message_found, message := false, ""
	reels_moved := false
	message_evidence := []string{click_evidence}
	previous, err := g.frame("after_click")
	if err != nil {
		return []check{error_check("Observar intento", err)}
	}
	for attempt := 0; attempt < 8 && !message_found; attempt++ {
		time.Sleep(time.Second)
		current, err := g.frame("attempt")
		if err != nil {
			return []check{error_check("Observar intento", err)}
		}
		if g.outer_reels_changed(previous, current) {
			reels_moved = true
			message_evidence = append(message_evidence, current)
		}
		if found, match, err := vision.find_text(current, s.config.InsufficientPatterns, nil); err == nil && found {
			message_found, message = true, match
			message_evidence = append(message_evidence, current)
		}
		previous = current
	}
	if !message_found {
		message_evidence = append(message_evidence, previous)
	}
	// Un giro rápido podría caer entre dos capturas: comparar también antes del clic con la última captura.
	if g.outer_reels_changed(click_evidence, previous) {
		reels_moved = true
	}

	checks := []check{}
	if message_found {
		checks = append(checks, check{"Mensaje de saldo insuficiente en español", PASS, fmt.Sprintf("texto detectado: %q", message), message_evidence})
	} else {
		checks = append(checks, check{"Mensaje de saldo insuficiente en español", INCONCLUSIVE, "no se leyó un mensaje reconocible (puede ser fallo de OCR)", message_evidence})
	}
	if reels_moved {
		checks = append(checks, check{"El intento no se convirtió en un giro", FAIL, "se observó movimiento de rodillos", message_evidence})
	} else {
		checks = append(checks, check{"El intento no se convirtió en un giro", PASS, "columnas exteriores de rodillos sin cambios tras el clic", message_evidence})
	}
	checks = append(checks, currency_check(before, betsson_before_text, before_evidence))

	// Cerrar el aviso no forma parte de la comprobación: se leen los importes tal como queden visibles.
	after, after_evidence, err := g.read_amounts("after")
	if err != nil {
		return append(checks, error_check("Lectura posterior del juego", err))
	}
	balance_before, before_ok := cents_value(before["game_balance"])
	balance_after, after_ok := cents_value(after["game_balance"])
	checks = append(checks, verdict("Saldo del juego sin cambios", balance_before == balance_after, before_ok && after_ok,
		fmt.Sprintf("antes %s, después %s", show(before["game_balance"]), show(after["game_balance"])),
		append(append([]string{}, before_evidence...), after_evidence...)))

	s.page.Goto(s.config.BaseURL)
	betsson_after, betsson_after_text, err := s.stable_betsson_balance(time.Duration(s.config.Timing.BalanceWaitS) * time.Second)
	if err != nil {
		return append(checks, error_check("Saldo Betsson después", err))
	}
	checks = append(checks, verdict("Saldo Betsson sin cambios", betsson_after == betsson_before, true,
		fmt.Sprintf("antes %s, después %s", betsson_before_text, betsson_after_text), nil))
	return checks
}

func show(reading region_reading) string {
	if reading.Cents == nil {
		reason := "ilegible"
		if reading.Error != nil {
			reason = *reading.Error
		}
		return fmt.Sprintf("desconocido (%s)", reason)
	}
	return format_cents(*reading.Cents)
}

func format_cents(cents int64) string {
	return fmt.Sprintf("%d,%02d €", cents/100, cents%100)
}

func ensure_dir(path string) error {
	return os.MkdirAll(path, 0o755)
}
