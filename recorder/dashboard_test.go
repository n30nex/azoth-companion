package main

import (
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"azoth/capture/internal/capture"
	"azoth/capture/internal/config"
	"azoth/capture/internal/journal"
)

func TestDashboardGuards(t *testing.T) {
	app := NewApp(config.Settings{OutputDir: t.TempDir()})
	app.j = journal.New(time.Now, "", nil)
	app.cap = capture.New(t.TempDir(), nil, nil)
	handler := app.dashboardHandler("test-secret")
	for _, tc := range []struct {
		method, path, body, token, origin string
		status                            int
	}{
		{"GET", "/state", "", "", "", 401},
		{"GET", "/state", "", "test-secret", "https://example.com", 401},
		{"GET", "/state", "", "test-secret", "", 200},
		{"POST", "/start", `{"name":"../bad","activity":"Combat","targets":[2818]}`, "test-secret", "", 400},
		{"POST", "/start", `{"name":"valid","activity":"Combat","targets":[2818,2818]}`, "test-secret", "", 400},
		{"POST", "/start", `{"name":"valid","activity":"Combat","targets":[2818],"exe":"something.exe"}`, "test-secret", "", 400},
		{"POST", "/stop", `{"started_ms":1}`, "test-secret", "", 409},
	} {
		request := httptest.NewRequest(tc.method, tc.path, strings.NewReader(tc.body))
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set("Authorization", "Bearer "+tc.token)
		if tc.origin != "" {
			request.Header.Set("Origin", tc.origin)
		}
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		if response.Code != tc.status {
			t.Fatalf("%s %s: got %d want %d: %s", tc.method, tc.path, response.Code, tc.status, response.Body.String())
		}
	}
	if app.j.State().Phase != journal.PhaseIdle {
		t.Fatal("Rejected commands changed the journal")
	}
	app.j.Start("existing", "Combat")
	request := httptest.NewRequest("POST", "/start", strings.NewReader(`{"name":"valid","activity":"Combat","targets":[2818]}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Authorization", "Bearer test-secret")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != 409 {
		t.Fatal("A second start was not rejected")
	}
}
