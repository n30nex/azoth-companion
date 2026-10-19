package main

import (
	"crypto/rand"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"syscall"
	"time"

	"azoth/capture/internal/config"
	"azoth/capture/internal/journal"
)

// This bridge only exposes the recorder's existing session controls on loopback.
// The original game launcher, capture implementation and hotkey stay unchanged.
func (a *App) startDashboard() {
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		a.emit("notice", "Dashboard connection unavailable: "+err.Error())
		return
	}
	secret := make([]byte, 32)
	if _, err = rand.Read(secret); err != nil {
		listener.Close()
		return
	}
	token := hex.EncodeToString(secret)
	bridgePath := filepath.Join(filepath.Dir(config.DraftPath()), "dashboard-bridge.json")
	body, _ := json.Marshal(map[string]any{"url": "http://" + listener.Addr().String(), "token": token, "pid": os.Getpid()})
	if err = os.WriteFile(bridgePath, body, 0600); err != nil {
		listener.Close()
		return
	}
	service := &http.Server{Handler: a.dashboardHandler(token), ReadHeaderTimeout: 5 * time.Second, IdleTimeout: 10 * time.Second}
	a.dashboardClose = func() { service.Close(); os.Remove(bridgePath) }
	go service.Serve(listener)
}

func (a *App) openDashboard() {
	path := filepath.Join(filepath.Dir(a.appDir()), "AzothCompanion", "Start-Companion.ps1")
	if _, err := os.Stat(path); err != nil {
		return
	}
	cmd := exec.Command("powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", path)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	go func() {
		if err := cmd.Run(); err != nil {
			a.emit("notice", "Open the Field Guide shortcut to reconnect the dashboard.")
		}
	}()
}

func (a *App) dashboardHandler(token string) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Cache-Control", "no-store")
		fail := func(status int, message string) {
			w.WriteHeader(status)
			json.NewEncoder(w).Encode(map[string]string{"error": message})
		}
		if r.Header.Get("Origin") != "" || subtle.ConstantTimeCompare([]byte(r.Header.Get("Authorization")), []byte("Bearer "+token)) != 1 {
			fail(http.StatusUnauthorized, "Recorder authorization required")
			return
		}
		if r.Method == "GET" && r.URL.Path == "/state" {
			a.mu.Lock()
			settings, hotkeyError := a.set, a.hkErr
			a.mu.Unlock()
			json.NewEncoder(w).Encode(map[string]any{"state": a.j.State(), "capture": a.cap.Status(), "ready": a.cap.IsEnvInstalled(), "hotkey_error": hotkeyError, "settings": settings, "bridge_version": 1})
			return
		}
		if r.Method != "POST" || r.Header.Get("Content-Type") != "application/json" {
			fail(405, "Use a JSON command")
			return
		}
		var command struct {
			Name      string `json:"name"`
			Activity  string `json:"activity"`
			Targets   []int  `json:"targets"`
			StartedMs int64  `json:"started_ms"`
		}
		decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&command); err != nil {
			fail(400, "Invalid recorder command")
			return
		}
		a.dashboardMu.Lock()
		defer a.dashboardMu.Unlock()
		state := a.j.State()
		switch r.URL.Path {
		case "/start":
			if state.Phase == journal.PhaseRunning {
				fail(409, "A recording is already running")
				return
			}
			if draft := a.j.CheckDraft(); draft.Found {
				fail(409, "Recover or discard the unfinished draft in Azoth Capture first")
				return
			}
			if !regexp.MustCompile(`^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$`).MatchString(command.Name) || len(command.Targets) < 1 || len(command.Targets) > 4 {
				fail(400, "Invalid session name or targets")
				return
			}
			seen := map[int]bool{}
			for _, id := range command.Targets {
				if id <= 0 || seen[id] {
					fail(400, "Invalid or repeated packet target")
					return
				}
				seen[id] = true
			}
			validActivity := false
			for _, activity := range journal.Activities {
				if activity == command.Activity {
					validActivity = true
				}
			}
			if !validActivity {
				fail(400, "Unknown activity")
				return
			}
			for _, path := range []string{filepath.Join(a.outputDir(), command.Name), filepath.Join(a.appDir(), "Aeternum-World", "Tools", "nw_capture", "captures", command.Name)} {
				if _, err := os.Stat(path); err == nil {
					fail(409, "Choose an unused session name")
					return
				}
			}
			tasks := exec.Command("tasklist.exe", "/FO", "CSV", "/NH")
			tasks.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
			output, err := tasks.Output()
			if err != nil {
				fail(503, "Could not check whether the game is already open")
				return
			}
			processes := strings.ToLower(string(output))
			if strings.Contains(processes, `"newworld.exe"`) {
				fail(409, "Close New World normally before starting a new capture")
				return
			}
			if !strings.Contains(processes, `"steam.exe"`) {
				fail(409, "Open Steam and sign in before starting a capture")
				return
			}
			a.mu.Lock()
			settings, hotkeyError := a.set, a.hkErr
			a.mu.Unlock()
			if hotkeyError != "" {
				fail(409, "The recorder hotkey is unavailable: "+hotkeyError)
				return
			}
			a.SetTargets(command.Targets)
			started, err := a.StartSession(settings.ExePath, command.Name, command.Activity, settings.Timeout, settings.OnePerEP)
			if err != nil {
				fail(409, err.Error())
				return
			}
			json.NewEncoder(w).Encode(started)
		case "/stop":
			if state.Phase != journal.PhaseRunning || command.StartedMs != state.StartedMs {
				fail(409, "That recording is not running")
				return
			}
			result, err := a.StopSession()
			if err != nil {
				fail(409, err.Error())
				return
			}
			json.NewEncoder(w).Encode(result)
		default:
			fail(404, fmt.Sprintf("Unknown recorder command: %s", r.URL.Path))
		}
	})
}
