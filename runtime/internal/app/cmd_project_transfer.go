package app

// Typed project actions run in the connector; native archive validation and
// filesystem delivery remain in the CLI.
import (
	"archive/zip"
	"bytes"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

const projectArchiveLimit = 16 * 1024 * 1024

func projectTransferRequest(cfg *appConfig, window, operation, uuid, pageUUID string) (*actionResult, map[string]any, error) {
	if strings.TrimSpace(window) == "" || strings.TrimSpace(uuid) == "" {
		return nil, nil, fmt.Errorf("explicit --window and --project-uuid are required")
	}
	if cfg.project != "" || cfg.doc != "" {
		return nil, nil, fmt.Errorf("project transfer uses --project-uuid and --window; omit global --project/--doc routing")
	}
	if operation != "open" && operation != "export" {
		return nil, nil, fmt.Errorf("unsupported project transfer operation %q", operation)
	}
	payload := map[string]any{"projectUuid": uuid}
	if operation == "open" {
		payload["allowDiscardUnsaved"] = true // caller has checked the explicit CLI flag
		if pageUUID != "" {
			payload["pageUuid"] = pageUUID
		}
	}
	res, err := requestActionTimed(cfg, "project."+operation, window, payload, 60*time.Second)
	if err != nil {
		return res, nil, err
	}
	value := res.Result
	if value["uuid"] != uuid {
		return res, nil, fmt.Errorf("project transfer returned missing or mismatched identity")
	}
	return res, value, nil
}

func writeProjectArchive(value map[string]any, out string) (map[string]any, error) {
	encoded, ok := value["base64"].(string)
	if !ok || len(encoded) > base64.StdEncoding.EncodedLen(projectArchiveLimit) {
		return nil, fmt.Errorf("invalid or oversized project archive envelope")
	}
	data, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil {
		return nil, fmt.Errorf("invalid project archive base64: %w", err)
	}
	size, ok := value["size"].(float64)
	if !ok || size != float64(len(data)) || len(data) == 0 || len(data) > projectArchiveLimit || value["format"] != "epro2" {
		return nil, fmt.Errorf("invalid project archive size/format")
	}
	if err = validateProjectZip(data, true); err != nil {
		return nil, err
	}
	if err = os.MkdirAll(filepath.Dir(out), 0755); err != nil {
		return nil, err
	}
	f, err := os.OpenFile(out, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0644)
	if err != nil {
		return nil, err
	}
	_, err = f.Write(data)
	closeErr := f.Close()
	if err != nil {
		return nil, err
	}
	if closeErr != nil {
		return nil, closeErr
	}
	absolute, err := filepath.Abs(out)
	if err != nil {
		return nil, err
	}
	return map[string]any{"uuid": value["uuid"], "format": "epro2", "path": absolute, "bytes": len(data), "sha256": fmt.Sprintf("%x", sha256.Sum256(data)), "zipIntegrityVerified": true, "restoreVerified": false}, nil
}

// validateProjectZip checks the ZIP container and CRCs without extracting
// user-controlled paths, bounding expanded data to avoid archive bombs.
func validateProjectZip(data []byte, requireEpru bool) error {
	z, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return fmt.Errorf("invalid native project ZIP: %w", err)
	}
	var expanded uint64
	native := false
	for _, f := range z.File {
		if f.UncompressedSize64 > 128*1024*1024-expanded {
			return fmt.Errorf("project archive expanded size exceeds 128 MiB")
		}
		expanded += f.UncompressedSize64
		if strings.HasSuffix(strings.ToLower(f.Name), ".epru") {
			native = true
		}
		r, e := f.Open()
		if e != nil {
			return e
		}
		_, e = io.Copy(io.Discard, io.LimitReader(r, int64(f.UncompressedSize64)+1))
		r.Close()
		if e != nil {
			return fmt.Errorf("project ZIP integrity: %w", e)
		}
	}
	if requireEpru && !native {
		return fmt.Errorf("native epro2 archive contains no epru project data")
	}
	return nil
}

func newProjectImportCmd(cfg *appConfig, window *string, stdout io.Writer) *cobra.Command {
	var file, name, team string
	var extract bool
	c := &cobra.Command{Use: "import", Short: "Import a native project archive as a NEW project (@beta importer; never overwrites)",
		Long: `Import an EasyEDA Pro project archive (.epro2, .epro, or a .zip packaging) as a new
project through the official @beta importer. The command never writes into an
existing project and does not open the result. The archive is checked for ZIP
integrity first; .epro2 must contain .epru data. Import success proves only
that a project was created: open it and read back schematic, PCB and DRC.
A timeout leaves the outcome unknown; run 'zhigou project find' before retrying.`,
		Example: `  zhigou project import --window <id> --file design.epro2 --name blink-import`,
		Args:    cobra.NoArgs, RunE: func(cmd *cobra.Command, args []string) error {
			if strings.TrimSpace(*window) == "" || strings.TrimSpace(name) == "" {
				return fmt.Errorf("explicit --window and --name are required")
			}
			if cfg.project != "" || cfg.doc != "" {
				return fmt.Errorf("project import uses --window; omit global --project/--doc routing")
			}
			ext := strings.ToLower(filepath.Ext(file))
			if ext != ".epro2" && ext != ".epro" && ext != ".zip" {
				return fmt.Errorf("--file must be an .epro2, .epro or .zip archive")
			}
			info, err := os.Stat(file)
			if err != nil {
				return err
			}
			if !info.Mode().IsRegular() || info.Size() == 0 || info.Size() > projectArchiveLimit {
				return fmt.Errorf("--file must be a regular file of 1 byte to 16 MiB")
			}
			data, err := os.ReadFile(file)
			if err != nil {
				return err
			}
			if err = validateProjectZip(data, ext == ".epro2"); err != nil {
				return err
			}
			payload := map[string]any{"fileName": filepath.Base(file), "base64": base64.StdEncoding.EncodeToString(data), "friendlyName": name}
			if team != "" {
				payload["teamUuid"] = team
			}
			if extract {
				payload["importOption"] = "ImportDocumentExtractLibraries"
			}
			res, err := requestActionTimed(cfg, "project.import", *window, payload, 150*time.Second)
			if err != nil {
				// The host may open the new project and reload the page mid-call
				// (live 4.1.71), dropping the connector before it responds.
				return fmt.Errorf("%w; outcome unknown: run `zhigou project find --name %q` before retrying", err, name)
			}
			if uuid, _ := res.Result["uuid"].(string); uuid == "" {
				return fmt.Errorf("project import returned no project identity")
			}
			res.Result["sourceSha256"] = fmt.Sprintf("%x", sha256.Sum256(data))
			res.Result["sourcePath"] = file
			return encodeResultEnvelope(res, res.Result, stdout)
		}}
	c.Flags().StringVar(&file, "file", "", "project archive to import (required)")
	c.Flags().StringVar(&name, "name", "", "friendly name of the new project (required)")
	c.Flags().StringVar(&team, "team-uuid", "", "owner team UUID (default: active project's team)")
	c.Flags().BoolVar(&extract, "extract-libraries", false, "also extract embedded libraries into the team library")
	return c
}

func newProjectExportCmd(cfg *appConfig, window *string, stdout io.Writer) *cobra.Command {
	var uuid, out string
	c := &cobra.Command{Use: "export", Short: "Export the active project as a native epro2 archive (no overwrite)", Args: cobra.NoArgs, RunE: func(cmd *cobra.Command, args []string) error {
		if out == "" || !strings.EqualFold(filepath.Ext(out), ".epro2") {
			return fmt.Errorf("--out must name a new .epro2 file")
		}
		if _, err := os.Stat(out); err == nil {
			return fmt.Errorf("output already exists: %s", out)
		} else if !os.IsNotExist(err) {
			return err
		}
		res, value, err := projectTransferRequest(cfg, *window, "export", uuid, "")
		if err != nil {
			return err
		}
		report, err := writeProjectArchive(value, out)
		if err != nil {
			return err
		}
		return encodeResultEnvelope(res, report, stdout)
	}}
	c.Flags().StringVar(&uuid, "project-uuid", "", "expected active project UUID (required)")
	c.Flags().StringVar(&out, "out", "", "new .epro2 output path (required); save documents before exporting")
	return c
}
