package main

import (
	"encoding/json"
	"fmt"
	"html/template"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
)

// ui_state es el estado de la interfaz local: una sola ejecución a la vez (las cuentas no admiten dos).
type ui_state struct {
	mutex   sync.Mutex
	options run_options
	running string
	log     []string
	results []case_result
	err     string
}

// serve_ui abre una interfaz web mínima (Go + htmx + Tailwind) solo en la máquina local.
func serve_ui(address string, options run_options) error {
	host, _, err := net.SplitHostPort(address)
	if err != nil {
		return err
	}
	if host != "localhost" && host != "127.0.0.1" {
		return fmt.Errorf("la interfaz solo se abre en localhost (usa localhost:PUERTO)")
	}
	state := &ui_state{options: options}
	state.results = latest_results(options.out_dir)

	mux := http.NewServeMux()
	mux.HandleFunc("GET /{$}", func(w http.ResponseWriter, r *http.Request) {
		PAGE.Execute(w, page_view{Config: options.config, Games: list_games()})
	})
	mux.HandleFunc("GET /status", state.render_status)
	mux.HandleFunc("POST /run", state.start_run)
	// Solo se sirven las capturas e informes de la carpeta de artefactos.
	mux.Handle("GET /files/", http.StripPrefix("/files/", http.FileServer(http.Dir(options.out_dir))))
	fmt.Printf("Interfaz en http://%s\n", address)
	return http.ListenAndServe(address, mux)
}

type page_view struct {
	Config market_config
	Games  []game_entry
}

func (state *ui_state) start_run(w http.ResponseWriter, r *http.Request) {
	only := r.URL.Query().Get("case")
	if only != "" && only != "T01" && only != "T02" {
		http.Error(w, "caso no válido", http.StatusBadRequest)
		return
	}
	state.mutex.Lock()
	if state.running == "" {
		if config, err := load_config(state.options.config_path, r.FormValue("game")); err != nil {
			state.err = err.Error()
		} else {
			options := state.options
			options.config = config
			label := only
			if label == "" {
				label = "T01 y T02"
			}
			state.running, state.log, state.err = label+" · "+config.GameName, nil, ""
			go state.run(options, only)
		}
	}
	state.mutex.Unlock()
	state.render_status(w, r)
}

func (state *ui_state) run(options run_options, only string) {
	progress := func(line string) {
		state.mutex.Lock()
		state.log = append(state.log, line)
		state.mutex.Unlock()
	}
	_, _, err := run_cases(options, only, progress)
	results := latest_results(options.out_dir)
	state.mutex.Lock()
	defer state.mutex.Unlock()
	state.running = ""
	if err != nil {
		state.err = err.Error()
	}
	state.results = results
}

type evidence_link struct {
	URL  string
	Name string
}

type check_view struct {
	check
	Links []evidence_link
}

type result_view struct {
	case_result
	Checks []check_view
	Passed int
}

type status_view struct {
	Running string
	Log     []string
	Err     string
	Results []result_view
}

func (state *ui_state) render_status(w http.ResponseWriter, r *http.Request) {
	state.mutex.Lock()
	view := status_view{Running: state.running, Log: append([]string{}, state.log...), Err: state.err}
	results := state.results
	state.mutex.Unlock()
	for _, result := range results {
		rv := result_view{case_result: result}
		for _, c := range result.Checks {
			cv := check_view{check: c}
			if c.Status == PASS {
				rv.Passed++
			}
			for _, path := range c.Evidence {
				relative, err := filepath.Rel(state.options.out_dir, path)
				if err != nil || strings.HasPrefix(relative, "..") {
					continue
				}
				cv.Links = append(cv.Links, evidence_link{"/files/" + filepath.ToSlash(relative), filepath.Base(path)})
			}
			rv.Checks = append(rv.Checks, cv)
		}
		view.Results = append(view.Results, rv)
	}
	STATUS.Execute(w, view)
}

// latest_results reúne el resultado más reciente de cada caso a partir de los informes guardados.
func latest_results(out_dir string) []case_result {
	entries, err := os.ReadDir(out_dir)
	if err != nil {
		return nil
	}
	names := []string{}
	for _, entry := range entries {
		if entry.IsDir() {
			names = append(names, entry.Name())
		}
	}
	sort.Sort(sort.Reverse(sort.StringSlice(names)))
	seen := map[string]bool{}
	latest := []case_result{}
	for _, name := range names {
		raw, err := os.ReadFile(filepath.Join(out_dir, name, "report.json"))
		if err != nil {
			continue
		}
		var results []case_result
		if json.Unmarshal(raw, &results) != nil {
			continue
		}
		for _, result := range results {
			if !seen[result.ID] {
				seen[result.ID] = true
				latest = append(latest, result)
			}
		}
	}
	sort.Slice(latest, func(i, j int) bool { return latest[i].ID < latest[j].ID })
	return latest
}

var FUNCS = template.FuncMap{
	"tone": func(status string) string {
		switch status {
		case PASS:
			return "text-ok bg-ok/10 ring-ok/30"
		case FAIL:
			return "text-bad bg-bad/10 ring-bad/30"
		case INCONCLUSIVE:
			return "text-warn bg-warn/10 ring-warn/30"
		default:
			return "text-mute bg-white/5 ring-white/10"
		}
	},
	"lower": strings.ToLower,
}

var PAGE = template.Must(template.New("page").Funcs(FUNCS).Parse(`<!doctype html>
<html lang="es" class="bg-ink">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Validación de juego</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Momo+Trust+Sans:wght@200..800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<script src="https://cdn.tailwindcss.com/3.4.5"></script>
<script>
tailwind.config = { theme: { extend: {
  colors: { ink: "#09090b", tile: "#131316", tile2: "#1a1a1e", line: "rgba(255,255,255,0.07)",
            text: "#f3f3f3", mute: "#8a8a8f", ok: "#24BA4A", bad: "#ff5c5c", warn: "#f5b642" },
  fontFamily: { sans: ["Momo Trust Sans", "ui-sans-serif", "system-ui"], mono: ["JetBrains Mono", "ui-monospace"] } } } }
</script>
<style>
  body { -webkit-font-smoothing: antialiased; }
  .tile { background: #131316; border: 1px solid rgba(255,255,255,0.07); border-radius: 22px; }
  .pill { border-radius: 999px; }
  select { appearance: none; }
</style>
</head>
<body class="bg-ink text-text font-sans min-h-screen">
<main class="max-w-6xl mx-auto px-4 py-8 sm:py-12">
  <div class="grid grid-cols-1 md:grid-cols-4 gap-4">

    <section class="tile p-6 md:col-span-2 md:row-span-2 flex flex-col justify-between min-h-[220px]">
      <div class="flex items-center gap-2 text-mute text-sm">
        <span class="w-2 h-2 rounded-full bg-ok"></span> betsson · pragmatic play · real play
      </div>
      <div>
        <h1 class="text-4xl sm:text-5xl font-semibold tracking-tight leading-[1.05]">validación<br>de juego.</h1>
        <p class="mt-3 text-mute max-w-sm">lo que ve el jugador, comprobado con capturas: giros, mensajes y saldos.</p>
      </div>
    </section>

    <section class="tile p-6">
      <p class="text-mute text-sm">mercado</p>
      <p class="mt-2 text-2xl font-semibold">{{.Config.Market}} · {{lower .Config.Language}}</p>
      <p class="mt-1 font-mono text-mute text-sm break-all">{{.Config.BaseURL}}</p>
    </section>
    <section class="tile p-6">
      <p class="text-mute text-sm">moneda</p>
      <p class="mt-2 text-2xl font-semibold font-mono">{{.Config.Currency}}</p>
      <p class="mt-1 text-mute text-sm">importes exactos en céntimos</p>
    </section>

    <section class="tile p-6 md:col-span-2">
      <form id="launcher" class="flex flex-col gap-4">
        <label class="text-mute text-sm" for="game">juego</label>
        <div class="relative">
          <select id="game" name="game" class="w-full bg-tile2 border border-line pill px-5 py-3 pr-10 text-text focus:outline-none focus:ring-2 focus:ring-ok/40">
            {{range .Games}}<option value="{{.ID}}" {{if not .Calibrated}}disabled{{end}} {{if eq .ID $.Config.GameID}}selected{{end}}>{{.Name}}{{if not .Calibrated}} · sin calibrar{{end}}</option>{{end}}
          </select>
          <span class="pointer-events-none absolute right-5 top-1/2 -translate-y-1/2 text-mute">⌄</span>
        </div>
        <div class="flex flex-wrap gap-2">
          <button hx-post="/run?case=T01" hx-include="#launcher" hx-target="#status" hx-confirm="T01 hace un giro con dinero real de la cuenta financiada. ¿Continuar?"
            class="pill px-5 py-2.5 bg-ok text-black font-semibold hover:brightness-110 transition">t01 · giro completado</button>
          <button hx-post="/run?case=T02" hx-include="#launcher" hx-target="#status"
            class="pill px-5 py-2.5 bg-text text-black font-semibold hover:brightness-90 transition">t02 · saldo insuficiente</button>
          <button hx-post="/run" hx-include="#launcher" hx-target="#status" hx-confirm="Incluye T01: un giro con dinero real. ¿Continuar?"
            class="pill px-5 py-2.5 border border-line text-text hover:bg-white/5 transition">ambos</button>
        </div>
      </form>
    </section>

    <section class="tile p-6 md:col-span-2">
      <p class="text-mute text-sm">juegos</p>
      <ul class="mt-3 flex flex-wrap gap-2">
        {{range .Games}}
        <li class="pill px-4 py-2 bg-tile2 border border-line text-sm flex items-center gap-2">
          <span class="w-1.5 h-1.5 rounded-full {{if .Calibrated}}bg-ok{{else}}bg-mute{{end}}"></span>{{lower .Name}}
        </li>
        {{end}}
      </ul>
      <p class="mt-3 text-mute text-xs">un juego nuevo se calibra con <span class="font-mono">-explore</span>, sin apostar.</p>
    </section>

    <section class="tile p-6 md:col-span-2">
      <p class="text-mute text-sm">cómo se decide</p>
      <ul class="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
        <li class="bg-tile2 rounded-2xl p-3"><span class="font-mono text-ok text-xs font-semibold">PASS</span><p class="text-mute mt-1">comprobado con evidencia</p></li>
        <li class="bg-tile2 rounded-2xl p-3"><span class="font-mono text-bad text-xs font-semibold">FAIL</span><p class="text-mute mt-1">fallo demostrado</p></li>
        <li class="bg-tile2 rounded-2xl p-3"><span class="font-mono text-warn text-xs font-semibold">INCONCLUSIVE</span><p class="text-mute mt-1">lectura dudosa: nunca cuenta como pass</p></li>
        <li class="bg-tile2 rounded-2xl p-3"><span class="font-mono text-mute text-xs font-semibold">ERROR</span><p class="text-mute mt-1">no se pudo ejecutar</p></li>
      </ul>
    </section>
  </div>

  <div id="status" hx-get="/status" hx-trigger="load, every 2s" class="mt-4"></div>

  <footer class="mt-10 text-center text-mute text-xs">sin evidencia completa no hay pass · ningún giro se reintenta solo</footer>
</main>
</body>
</html>`))

var STATUS = template.Must(template.New("status").Funcs(FUNCS).Parse(`
<div class="grid grid-cols-1 md:grid-cols-4 gap-4">
{{if .Running}}
  <section class="tile p-6 md:col-span-4 ring-1 ring-ok/30">
    <div class="flex items-center gap-3">
      <span class="relative flex h-2.5 w-2.5"><span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-ok opacity-60"></span><span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-ok"></span></span>
      <p class="font-semibold">ejecutando {{lower .Running}}…</p>
    </div>
    <pre class="mt-4 bg-ink rounded-2xl p-4 text-xs font-mono text-mute whitespace-pre-wrap max-h-64 overflow-auto">{{range .Log}}{{.}}
{{else}}iniciando sesión y abriendo el juego…{{end}}</pre>
  </section>
{{end}}
{{if .Err}}
  <section class="tile p-6 md:col-span-4 ring-1 ring-bad/30">
    <p class="text-bad font-semibold">error de ejecución</p>
    <p class="mt-1 text-mute text-sm break-words">{{.Err}}</p>
  </section>
{{end}}

{{range $r := .Results}}
  <section class="tile p-6 md:col-span-2 flex flex-col gap-5">
    <div class="flex items-start justify-between gap-3">
      <div>
        <p class="text-mute text-sm font-mono">{{lower $r.ID}} · {{$r.Market}}</p>
        <h2 class="mt-1 text-2xl font-semibold">{{lower $r.Scenario}}</h2>
        <p class="text-mute text-sm">{{lower $r.Game}}</p>
      </div>
      <span class="pill px-3 py-1 text-xs font-semibold font-mono ring-1 {{tone $r.Status}}">{{$r.Status}}</span>
    </div>
    <div class="grid grid-cols-2 gap-2">
      {{with index $r.Figures "betsson_before"}}<div class="bg-tile2 rounded-2xl p-3"><p class="text-mute text-xs">betsson antes</p><p class="font-mono text-lg">{{.}}</p></div>{{end}}
      {{with index $r.Figures "betsson_after"}}<div class="bg-tile2 rounded-2xl p-3"><p class="text-mute text-xs">betsson después</p><p class="font-mono text-lg">{{.}}</p></div>{{end}}
      {{with index $r.Figures "bet"}}<div class="bg-tile2 rounded-2xl p-3"><p class="text-mute text-xs">apuesta</p><p class="font-mono text-lg">{{.}}</p></div>{{end}}
      {{with index $r.Figures "win"}}<div class="bg-tile2 rounded-2xl p-3"><p class="text-mute text-xs">premio</p><p class="font-mono text-lg">{{.}}</p></div>{{end}}
      {{with index $r.Figures "message"}}<div class="bg-tile2 rounded-2xl p-3"><p class="text-mute text-xs">mensaje</p><p class="text-sm">{{.}}</p></div>{{end}}
    </div>
    <p class="text-mute text-sm"><span class="text-text font-semibold">{{$r.Passed}}/{{len $r.Checks}}</span> comprobaciones en pass</p>
  </section>
{{end}}

{{range $r := .Results}}
  <section class="tile p-6 md:col-span-2">
    <p class="text-mute text-sm font-mono">{{lower $r.ID}} · comprobaciones</p>
    <ul class="mt-4 flex flex-col gap-3">
      {{range $r.Checks}}
      <li class="bg-tile2 rounded-2xl p-4">
        <div class="flex items-start gap-3">
          <span class="shrink-0 pill px-2.5 py-0.5 text-[11px] font-semibold font-mono ring-1 {{tone .Status}}">{{.Status}}</span>
          <div class="min-w-0">
            <p class="font-medium leading-snug">{{lower .Name}}</p>
            <p class="mt-1 text-mute text-sm break-words">{{.Detail}}</p>
          </div>
        </div>
        {{if .Links}}
        <div class="mt-3 flex gap-2 overflow-x-auto pb-1">
          {{range .Links}}<a href="{{.URL}}" target="_blank" title="{{.Name}}" class="shrink-0"><img src="{{.URL}}" alt="{{.Name}}" loading="lazy" class="h-16 rounded-xl ring-1 ring-line hover:ring-ok/50 transition"></a>{{end}}
        </div>
        {{end}}
      </li>
      {{end}}
    </ul>
  </section>
{{else}}
  {{if not .Running}}<section class="tile p-6 md:col-span-4 text-mute">aún no hay informes. lanza un caso.</section>{{end}}
{{end}}
</div>
`))
