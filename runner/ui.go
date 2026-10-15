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
	run_dir string
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
	state.run_dir, state.results = latest_report(options.out_dir)

	mux := http.NewServeMux()
	mux.HandleFunc("GET /{$}", func(w http.ResponseWriter, r *http.Request) {
		PAGE.Execute(w, options.config)
	})
	mux.HandleFunc("GET /status", state.render_status)
	mux.HandleFunc("POST /run", state.start_run)
	// Solo se sirven las capturas e informes de la carpeta de artefactos.
	mux.Handle("GET /files/", http.StripPrefix("/files/", http.FileServer(http.Dir(options.out_dir))))
	fmt.Printf("Interfaz en http://%s\n", address)
	return http.ListenAndServe(address, mux)
}

func (state *ui_state) start_run(w http.ResponseWriter, r *http.Request) {
	only := r.URL.Query().Get("case")
	if only != "" && only != "T01" && only != "T02" {
		http.Error(w, "caso no válido", http.StatusBadRequest)
		return
	}
	state.mutex.Lock()
	if state.running == "" {
		label := only
		if label == "" {
			label = "T01 y T02"
		}
		state.running, state.log, state.err = label, nil, ""
		go state.run(only)
	}
	state.mutex.Unlock()
	state.render_status(w, r)
}

func (state *ui_state) run(only string) {
	progress := func(line string) {
		state.mutex.Lock()
		state.log = append(state.log, line)
		state.mutex.Unlock()
	}
	_, results, err := run_cases(state.options, only, progress)
	state.mutex.Lock()
	defer state.mutex.Unlock()
	state.running = ""
	if err != nil {
		state.err = err.Error()
	}
	if results != nil {
		state.run_dir, state.results = latest_report(state.options.out_dir)
	}
}

type evidence_link struct {
	URL  string
	Name string
}

type status_view struct {
	Running string
	Log     []string
	Err     string
	RunDir  string
	Results []case_result
	Links   map[string][]evidence_link // por "caso/comprobación"
}

func (state *ui_state) render_status(w http.ResponseWriter, r *http.Request) {
	state.mutex.Lock()
	view := status_view{
		Running: state.running,
		Log:     append([]string{}, state.log...),
		Err:     state.err,
		RunDir:  filepath.Base(state.run_dir),
		Results: state.results,
		Links:   map[string][]evidence_link{},
	}
	state.mutex.Unlock()
	for _, result := range view.Results {
		for _, c := range result.Checks {
			for _, path := range c.Evidence {
				relative, err := filepath.Rel(state.options.out_dir, path)
				if err != nil || strings.HasPrefix(relative, "..") {
					continue
				}
				key := result.ID + "/" + c.Name
				view.Links[key] = append(view.Links[key], evidence_link{"/files/" + filepath.ToSlash(relative), filepath.Base(path)})
			}
		}
	}
	STATUS.Execute(w, view)
}

// latest_report reúne el resultado más reciente de cada caso a partir de los informes guardados.
func latest_report(out_dir string) (string, []case_result) {
	entries, err := os.ReadDir(out_dir)
	if err != nil {
		return "", nil
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
	newest := ""
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
				if newest == "" {
					newest = filepath.Join(out_dir, name)
				}
			}
		}
	}
	sort.Slice(latest, func(i, j int) bool { return latest[i].ID < latest[j].ID })
	return newest, latest
}

var FUNCS = template.FuncMap{
	"badge": func(status string) string {
		switch status {
		case PASS:
			return "bg-green-100 text-green-800"
		case FAIL:
			return "bg-red-100 text-red-800"
		case INCONCLUSIVE:
			return "bg-amber-100 text-amber-800"
		default:
			return "bg-gray-200 text-gray-800"
		}
	},
	"key": func(id, name string) string { return id + "/" + name },
}

var PAGE = template.Must(template.New("page").Parse(`<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Validación de juego — betsson.es</title>
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<script src="https://cdn.tailwindcss.com/3.4.5"></script>
</head>
<body class="bg-slate-50 text-slate-900">
<main class="max-w-5xl mx-auto p-4 sm:p-8 space-y-6">
  <header>
    <h1 class="text-2xl font-bold">Validación de juego</h1>
    <p class="text-slate-600">Mercado {{.Market}} · {{.Language}} · {{.Currency}} · {{.GameName}} (Pragmatic Play, Real Play)</p>
  </header>
  <section class="flex flex-wrap gap-3">
    <button hx-post="/run?case=T01" hx-target="#status" hx-confirm="T01 hace un giro con dinero real de la cuenta financiada. ¿Continuar?"
      class="px-4 py-2 rounded bg-orange-600 text-white font-semibold hover:bg-orange-700">T01 · Giro completado</button>
    <button hx-post="/run?case=T02" hx-target="#status"
      class="px-4 py-2 rounded bg-slate-700 text-white font-semibold hover:bg-slate-800">T02 · Saldo insuficiente</button>
    <button hx-post="/run" hx-target="#status" hx-confirm="Incluye T01: un giro con dinero real. ¿Continuar?"
      class="px-4 py-2 rounded border border-slate-400 font-semibold hover:bg-slate-100">Ambos</button>
  </section>
  <section id="status" hx-get="/status" hx-trigger="load, every 2s"></section>
</main>
</body>
</html>`))

var STATUS = template.Must(template.New("status").Funcs(FUNCS).Parse(`
{{if .Running}}
  <div class="rounded border border-orange-300 bg-orange-50 p-4">
    <p class="font-semibold">Ejecutando {{.Running}}…</p>
    <pre class="mt-2 text-xs whitespace-pre-wrap">{{range .Log}}{{.}}
{{end}}</pre>
  </div>
{{end}}
{{if .Err}}<div class="rounded border border-red-300 bg-red-50 p-4 text-red-800">Error de ejecución: {{.Err}}</div>{{end}}
{{if .Results}}
  <h2 class="text-lg font-semibold mt-2">Último resultado de cada caso</h2>
  {{$links := .Links}}
  {{range $r := .Results}}
  <div class="rounded bg-white shadow p-4 mt-3">
    <div class="flex items-center justify-between gap-2">
      <h3 class="font-semibold">{{$r.ID}} · {{$r.Scenario}} · {{$r.Market}}</h3>
      <span class="px-2 py-1 rounded text-sm font-bold {{badge $r.Status}}">{{$r.Status}}</span>
    </div>
    <ul class="mt-3 divide-y">
      {{range $c := $r.Checks}}
      <li class="py-2">
        <div class="flex items-start gap-2">
          <span class="shrink-0 px-2 rounded text-xs font-bold {{badge $c.Status}}">{{$c.Status}}</span>
          <div class="min-w-0">
            <p class="font-medium">{{$c.Name}}</p>
            <p class="text-sm text-slate-600 break-words">{{$c.Detail}}</p>
            <div class="flex flex-wrap gap-2 mt-1">
              {{range index $links (key $r.ID $c.Name)}}
              <a href="{{.URL}}" target="_blank" title="{{.Name}}"><img src="{{.URL}}" alt="{{.Name}}" class="h-16 rounded border"></a>
              {{end}}
            </div>
          </div>
        </div>
      </li>
      {{end}}
    </ul>
  </div>
  {{end}}
{{else if not .Running}}
  <p class="text-slate-500">Aún no hay informes. Lanza un caso.</p>
{{end}}
`))
