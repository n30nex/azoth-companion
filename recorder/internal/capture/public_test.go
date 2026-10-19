package capture

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
	"testing"
	"time"
)

func TestPinnedInstaller(t *testing.T) {
	var manifest map[string]json.RawMessage
	if err := json.Unmarshal(downloadLock, &manifest); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"python", "pip", "engine"} {
		var entry struct {
			URL string `json:"url"`
			SHA string `json:"sha256"`
		}
		if err := json.Unmarshal(manifest[name], &entry); err != nil {
			t.Fatal(err)
		}
		if !regexp.MustCompile(`^https://`).MatchString(entry.URL) || !regexp.MustCompile(`^[a-f0-9]{64}$`).MatchString(entry.SHA) {
			t.Fatalf("unlocked download: %s", name)
		}
	}
	for _, bad := range []string{"Remove-Item -Recurse", "Invoke-Expression", "git reset", "$HOME ="} {
		if bytes.Contains(installScript, []byte(bad)) {
			t.Fatalf("unsafe installer operation: %s", bad)
		}
	}
}

func TestReadinessDoesNotResetRecording(t *testing.T) {
	r := New(t.TempDir(), nil, nil)
	for _, path := range []string{r.pythonExe(), r.captureScript(), filepath.Join(r.rootDir, ".runtime-ready.json")} {
		os.MkdirAll(filepath.Dir(path), 0755)
		os.WriteFile(path, []byte("fixture"), 0600)
	}
	r.setStatus(StatusRunning)
	if !r.IsEnvInstalled() || r.Status() != StatusRunning {
		t.Fatal("checking readiness changed a running recorder")
	}
}

func TestStopWaitsForWriter(t *testing.T) {
	r := New(t.TempDir(), nil, nil)
	r.done = make(chan struct{})
	canceled := make(chan struct{})
	r.cancel = func() { close(canceled) }
	go func() { <-canceled; time.Sleep(25 * time.Millisecond); close(r.done) }()
	if err := r.StopCapture(); err != nil {
		t.Fatal(err)
	}
	select {
	case <-r.done:
	default:
		t.Fatal("export can race the active writer")
	}
}
