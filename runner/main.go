// runner orquesta los casos: abre Betsson con Playwright, pide a la visión en Python que interprete
// las capturas del juego, decide PASS/FAIL/INCONCLUSIVE/ERROR y escribe el informe con sus evidencias.
package main

import (
	"bufio"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// test_case une un escenario con su cuenta; el mercado viene de la configuración.
type test_case struct {
	id       string
	scenario string
	account  string
	run      func(*session, *vision_client, string, map[string]string) []check
}

var CASES = []test_case{
	{"T01", "Giro completado", "funded", run_completed_spin},
	{"T02", "Saldo insuficiente", "empty", run_insufficient_balance},
}

func main() {
	config_path := flag.String("config", "config/es.json", "configuración del mercado")
	game_id := flag.String("game", "", "juego (carpeta en config/games/); por defecto el del mercado")
	only := flag.String("case", "", "ejecutar solo este caso (T01 o T02)")
	explore := flag.String("explore", "", "solo calibración: iniciar sesión con esta cuenta (funded/empty), abrir el juego y capturar, sin apostar")
	headed := flag.Bool("headed", false, "mostrar el navegador")
	out_dir := flag.String("out", "artifacts", "carpeta del informe y las evidencias")
	python_path := flag.String("python", "vision/.venv/bin/python", "intérprete de Python de la visión")
	serve := flag.String("serve", "", "abrir la interfaz local en esta dirección (p. ej. localhost:8080)")
	flag.Parse()

	load_dotenv(".env")
	config, err := load_config(*config_path, *game_id)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	options := run_options{config: config, config_path: *config_path, out_dir: *out_dir, python_path: *python_path, headed: *headed}

	if *serve != "" {
		if err := serve_ui(*serve, options); err != nil {
			fmt.Fprintln(os.Stderr, "interfaz:", err)
			os.Exit(2)
		}
		return
	}
	if *explore != "" {
		run_dir := filepath.Join(*out_dir, time.Now().Format("20060102-150405"))
		if err := ensure_dir(run_dir); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(2)
		}
		if err := run_explore(config, *explore, run_dir, *headed); err != nil {
			fmt.Fprintln(os.Stderr, "exploración:", err)
			os.Exit(1)
		}
		return
	}
	run_dir, results, err := run_cases(options, *only, func(line string) { fmt.Println(line) })
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	fmt.Println("Informe:", filepath.Join(run_dir, "report.md"))
	for _, r := range results {
		if r.Status != PASS {
			os.Exit(1)
		}
	}
}

type run_options struct {
	config      market_config
	config_path string
	out_dir     string
	python_path string
	headed      bool
}

// run_cases ejecuta los casos (todos o solo `only`), escribe el informe y avisa del progreso con `progress`.
func run_cases(options run_options, only string, progress func(string)) (string, []case_result, error) {
	config := options.config
	if !config.Calibrated {
		return "", nil, fmt.Errorf("el juego %s no está calibrado: usa -explore y completa config/games/%s/profile.json", config.GameName, config.GameID)
	}
	run_dir := filepath.Join(options.out_dir, time.Now().Format("20060102-150405"))
	if err := ensure_dir(run_dir); err != nil {
		return "", nil, err
	}
	vision, err := start_vision(options.python_path, "vision/vision_server.py")
	if err != nil {
		return run_dir, nil, err
	}
	defer vision.close()

	results := []case_result{}
	for _, tc := range CASES {
		if only != "" && only != tc.id {
			continue
		}
		progress(fmt.Sprintf("== %s %s (%s)", tc.id, tc.scenario, config.Market))
		figures := map[string]string{}
		checks := run_case(tc, config, vision, run_dir, options.headed, figures)
		result := case_result{tc.id, config.Market, tc.scenario, config.GameName, config.GameID, overall(checks), checks, figures}
		for _, c := range checks {
			progress(fmt.Sprintf("   %-13s %s — %s", c.Status, c.Name, c.Detail))
		}
		progress(fmt.Sprintf("   => %s", result.Status))
		results = append(results, result)
	}
	if err := write_report(run_dir, results); err != nil {
		return run_dir, results, fmt.Errorf("no se pudo escribir el informe: %w", err)
	}
	return run_dir, results, nil
}

func run_case(tc test_case, config market_config, vision *vision_client, run_dir string, headed bool, figures map[string]string) []check {
	acc := config.Accounts[tc.account]
	user, password := os.Getenv(acc.UserEnv), os.Getenv(acc.PassEnv)
	if user == "" || password == "" {
		return []check{error_check("Credenciales", fmt.Errorf("faltan %s / %s en el entorno", acc.UserEnv, acc.PassEnv))}
	}
	case_dir := filepath.Join(run_dir, tc.id)
	if err := ensure_dir(case_dir); err != nil {
		return []check{error_check("Preparar evidencias", err)}
	}
	s, err := open_session(config, headed)
	if err != nil {
		return []check{error_check("Abrir navegador", err)}
	}
	defer s.close()
	// El login se reintenta una vez (la web falla a ratos); un rechazo explícito del WAF no se reintenta.
	if err := s.login(user, password); err != nil {
		if strings.Contains(err.Error(), "rechazó") {
			return []check{error_check("Iniciar sesión", err)}
		}
		fmt.Println("   reintento de inicio de sesión:", err)
		if err := s.login(user, password); err != nil {
			return []check{error_check("Iniciar sesión", err)}
		}
	}
	return tc.run(s, vision, case_dir, figures)
}

// load_dotenv carga variables de .env sin sobrescribir las que ya existen ni imprimirlas.
func load_dotenv(path string) {
	file, err := os.Open(path)
	if err != nil {
		return
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, value, found := strings.Cut(line, "=")
		if found && os.Getenv(key) == "" {
			os.Setenv(strings.TrimSpace(key), strings.Trim(strings.TrimSpace(value), `"'`))
		}
	}
}

// run_explore abre el juego y guarda capturas para calibrar regiones. Nunca pulsa el giro.
func run_explore(config market_config, account_name string, run_dir string, headed bool) error {
	s, err := open_session(config, headed)
	if err != nil {
		return err
	}
	defer s.close()
	// "anon" abre la página del juego sin sesión: sirve para comprobar rutas sin gastar intentos de login.
	if account_name == "anon" {
		if _, err := s.page.Goto(config.BaseURL + config.GamePath); err != nil {
			return err
		}
		s.dismiss_cookies()
		time.Sleep(5 * time.Second)
		title, _ := s.page.Title()
		iframes, _ := s.page.Locator("iframe").Count()
		fmt.Printf("url=%s título=%q iframes=%d\n", s.page.URL(), title, iframes)
		s.debug_shot("anon_game_page")
		return nil
	}
	acc := config.Accounts[account_name]
	user, password := os.Getenv(acc.UserEnv), os.Getenv(acc.PassEnv)
	if user == "" || password == "" {
		return fmt.Errorf("faltan %s / %s en el entorno", acc.UserEnv, acc.PassEnv)
	}
	if err := s.login(user, password); err != nil {
		return err
	}
	_, balance_text, err := s.betsson_balance()
	fmt.Println("saldo Betsson:", balance_text, err)
	rect, err := s.open_game()
	if err != nil {
		return err
	}
	fmt.Printf("juego en x=%.0f y=%.0f ancho=%.0f alto=%.0f, url=%s\n", rect.X, rect.Y, rect.Width, rect.Height, s.page.URL())
	vision, err := start_vision("vision/.venv/bin/python", "vision/vision_server.py")
	if err != nil {
		return err
	}
	defer vision.close()
	g := &game_run{s: s, vision: vision, rect: rect, dir: run_dir}
	// Juego nuevo con plantilla de carga pero sin la de giro: se entra y se captura el marcador.
	if config.SplashTemplate.Path != "" && config.SpinTemplate.Path == "" {
		fmt.Println("juego sin plantilla de giro: se entra al juego y se captura el marcador, sin girar")
		var splash location
		for attempt := 0; attempt < 20 && !splash.Found; attempt++ {
			time.Sleep(3 * time.Second)
			path, err := g.frame("loading")
			if err != nil {
				return err
			}
			if splash, err = g.find(path, config.SplashTemplate); err != nil {
				return err
			}
		}
		if !splash.Found {
			return fmt.Errorf("no se encontró el botón de la pantalla de carga")
		}
		if err := s.click_in_game(rect, [2]float64{*splash.X, *splash.Y}); err != nil {
			return err
		}
		for i := 0; i < 3; i++ {
			time.Sleep(4 * time.Second)
			if _, err := g.frame("explore"); err != nil {
				return err
			}
		}
		return nil
	}
	// Sin plantillas todavía (juego nuevo): solo se captura la pantalla de carga para recortarlas.
	if config.SplashTemplate.Path == "" || config.SpinTemplate.Path == "" {
		fmt.Println("juego sin plantillas: se capturan pantallas para calibrar, sin pulsar nada")
		for i := 0; i < 6; i++ {
			time.Sleep(4 * time.Second)
			if _, err := g.frame("explore"); err != nil {
				return err
			}
		}
		return nil
	}
	if err := g.enter_game(); err != nil {
		return err
	}
	for i := 0; i < 3; i++ {
		time.Sleep(3 * time.Second)
		if _, err := g.frame("explore"); err != nil {
			return err
		}
	}
	return nil
}
