package journal

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestPowerLossRecovery(t *testing.T) {
	path := filepath.Join(t.TempDir(), "draft.json")
	now := time.UnixMilli(1700000000000)
	j := New(func() time.Time { now = now.Add(time.Millisecond); return now }, path, nil)
	if _, err := j.Start("recover", "Other"); err != nil {
		t.Fatal(err)
	}
	stale, _ := os.ReadFile(path)
	at := now.Add(time.Second)
	if _, err := j.Mark(at, ViaHotkey, "Preserve this exact time", nil); err != nil {
		t.Fatal(err)
	}
	log := filepath.Join(filepath.Dir(path), "journals", "1700000000001.jsonl")
	f, err := os.OpenFile(log, os.O_APPEND|os.O_WRONLY, 0)
	if err != nil {
		t.Fatal(err)
	}
	f.WriteString(`{"schema":1,"steps":[`)
	f.Close()
	for _, damaged := range [][]byte{stale, make([]byte, 500)} {
		if err := os.WriteFile(path, damaged, 0600); err != nil {
			t.Fatal(err)
		}
		recovered, err := New(nil, path, nil).Recover()
		if err != nil || len(recovered.Steps) != 1 || recovered.Steps[0].TMs != at.UnixMilli() {
			t.Fatalf("lost marker: %+v %v", recovered, err)
		}
	}
	// The first mark after recovery must survive even if a partial log tail remains.
	j.Recover()
	j.Mark(at.Add(time.Second), ViaHotkey, "After recovery", nil)
	os.WriteFile(path, make([]byte, 500), 0600)
	recovered, err := New(nil, path, nil).Recover()
	if err != nil || len(recovered.Steps) != 2 {
		t.Fatalf("lost first post-recovery mark: %+v %v", recovered, err)
	}
	j.DiscardDraft()
	if New(nil, path, nil).CheckDraft().Found {
		t.Fatal("discarded session returned")
	}
}

func TestExportedSnapshotNotOffered(t *testing.T) {
	path := filepath.Join(t.TempDir(), "draft.json")
	j := New(nil, path, nil)
	j.Start("exported", "Other")
	j.Stop()
	j.markExported(t.TempDir())
	os.WriteFile(path, make([]byte, 100), 0600)
	if New(nil, path, nil).CheckDraft().Found {
		t.Fatal("exported session returned")
	}
}
