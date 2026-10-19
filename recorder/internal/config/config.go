package config

import (
	"encoding/json"
	"os"
	"path/filepath"

	"golang.org/x/sys/windows"
)

const DefaultHotkey = "F8"

type Settings struct {
	Hotkey      string `json:"hotkey"`
	AlwaysOnTop bool   `json:"always_on_top"`
	OutputDir   string `json:"output_dir"`
	ExePath     string `json:"exe_path"`
	Timeout     int    `json:"timeout"`
	OnePerEP    bool   `json:"one_per_endpoint"`
}

func DataDir() string {
	if d := os.Getenv("AZOTH_CAPTURE_DATA"); d != "" {
		return d
	}
	if d := os.Getenv("LOCALAPPDATA"); d != "" {
		return filepath.Join(d, "AzothCompanion", "recorder")
	}
	d, _ := os.UserConfigDir()
	return filepath.Join(d, "AzothCompanion", "recorder")
}

func DraftPath() string { return filepath.Join(DataDir(), "draft.json") }

func DefaultOutputDir() string {
	if d, err := windows.KnownFolderPath(windows.FOLDERID_Documents, 0); err == nil && d != "" {
		return filepath.Join(d, "Azoth Captures")
	}
	home, _ := os.UserHomeDir()
	return filepath.Join(home, "Documents", "Azoth Captures")
}

func settingsPath() string { return filepath.Join(DataDir(), "settings.json") }

func Load() Settings {
	s := Settings{}
	if b, err := os.ReadFile(settingsPath()); err == nil {
		json.Unmarshal(b, &s)
	}
	if s.Hotkey == "" {
		s.Hotkey = DefaultHotkey
	}
	if s.OutputDir == "" {
		s.OutputDir = DefaultOutputDir()
	}
	if s.Timeout == 0 {
		s.Timeout = 600
	}
	return s
}

func Save(s Settings) error {
	if err := os.MkdirAll(DataDir(), 0o755); err != nil {
		return err
	}
	b, _ := json.MarshalIndent(s, "", "  ")
	tmp := settingsPath() + ".tmp"
	f, err := os.OpenFile(tmp, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o600)
	if err != nil {
		return err
	}
	_, err = f.Write(b)
	if err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	return os.Rename(tmp, settingsPath())
}
