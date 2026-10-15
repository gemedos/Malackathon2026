package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

const GAMES_DIR = "config/games"

// market_config es la configuración de una ejecución: el mercado (config/<mercado>.json) más el perfil
// del juego (config/games/<juego>/profile.json), que aporta la calibración visual.
type market_config struct {
	Market               string             `json:"market"`
	BaseURL              string             `json:"base_url"`
	Language             string             `json:"language"`
	Currency             string             `json:"currency"`
	DefaultGame          string             `json:"default_game"`
	Accounts             map[string]account `json:"accounts"`
	InsufficientPatterns []string           `json:"insufficient_patterns"`
	Timing               struct {
		SpinTimeoutS        int `json:"spin_timeout_s"`
		PollIntervalMs      int `json:"poll_interval_ms"`
		StillFramesToSettle int `json:"still_frames_to_settle"`
		BalanceWaitS        int `json:"balance_wait_s"`
	} `json:"timing"`

	// Perfil del juego
	GameID          string                `json:"-"`
	Provider        string                `json:"provider"`
	Calibrated      bool                  `json:"calibrated"`
	GameName        string                `json:"game_name"`
	GamePath        string                `json:"game_path"`
	CalibrationNote string                `json:"calibration_note"`
	Regions         map[string][4]float64 `json:"regions"`
	AmountTextHSV   *[2][3]int            `json:"amount_text_hsv"`
	WinIdlePatterns []string              `json:"win_idle_patterns"`
	SplashTemplate  template_config       `json:"splash_template"`
	SpinTemplate    template_config       `json:"spin_template"`
	// "pixel" (por defecto) o "cells" para juegos con animación en reposo (ver vision_server.py).
	MotionMode string `json:"motion_mode"`
	ReelGrid   [2]int `json:"reel_grid"` // [columnas, filas] de rodillos, para el modo "cells"
}

type template_config struct {
	Path           string  `json:"path"`
	ReferenceWidth int     `json:"reference_width"`
	Threshold      float64 `json:"threshold"`
}

type account struct {
	UserEnv string `json:"user_env"`
	PassEnv string `json:"pass_env"`
}

// load_config lee el mercado y le superpone el perfil del juego (game_id vacío = juego por defecto).
func load_config(market_path, game_id string) (market_config, error) {
	var config market_config
	raw, err := os.ReadFile(market_path)
	if err != nil {
		return config, fmt.Errorf("no se pudo leer la configuración del mercado: %w", err)
	}
	if err := json.Unmarshal(raw, &config); err != nil {
		return config, fmt.Errorf("configuración del mercado no válida: %w", err)
	}
	if game_id == "" {
		game_id = config.DefaultGame
	}
	game_dir := filepath.Join(GAMES_DIR, game_id)
	raw, err = os.ReadFile(filepath.Join(game_dir, "profile.json"))
	if err != nil {
		return config, fmt.Errorf("juego %q desconocido (no existe %s/profile.json)", game_id, game_dir)
	}
	if err := json.Unmarshal(raw, &config); err != nil {
		return config, fmt.Errorf("perfil del juego %s no válido: %w", game_id, err)
	}
	config.GameID = game_id
	// Las plantillas se guardan junto al perfil del juego.
	for _, template := range []*template_config{&config.SplashTemplate, &config.SpinTemplate} {
		if template.Path != "" {
			template.Path = filepath.Join(game_dir, template.Path)
		}
	}
	return config, nil
}

type game_entry struct {
	ID         string
	Name       string
	Calibrated bool
}

// list_games devuelve los juegos con perfil en config/games, calibrados primero.
func list_games() []game_entry {
	entries, _ := os.ReadDir(GAMES_DIR)
	games := []game_entry{}
	for _, entry := range entries {
		raw, err := os.ReadFile(filepath.Join(GAMES_DIR, entry.Name(), "profile.json"))
		if err != nil {
			continue
		}
		var profile struct {
			Name       string `json:"game_name"`
			Calibrated bool   `json:"calibrated"`
		}
		if json.Unmarshal(raw, &profile) == nil {
			games = append(games, game_entry{entry.Name(), profile.Name, profile.Calibrated})
		}
	}
	sort.Slice(games, func(i, j int) bool {
		if games[i].Calibrated != games[j].Calibrated {
			return games[i].Calibrated
		}
		return games[i].Name < games[j].Name
	})
	return games
}
