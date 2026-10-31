package app

import (
	"compress/gzip"
	"fmt"
	"io"
	"os"
)

// gzipFile compresses path into path+".gz" and removes the original only after
// the compressed copy is fully written and closed - a half-written .gz would be
// worse than the large file it replaced.
func gzipFile(path string) error {
	src, err := os.Open(path)
	if err != nil {
		return err
	}
	defer src.Close()

	target := path + ".gz"
	out, err := os.Create(target)
	if err != nil {
		return err
	}
	writer := gzip.NewWriter(out)
	if _, err := io.Copy(writer, src); err != nil {
		writer.Close()
		out.Close()
		os.Remove(target)
		return fmt.Errorf("compress %s: %w", path, err)
	}
	if err := writer.Close(); err != nil {
		out.Close()
		os.Remove(target)
		return err
	}
	if err := out.Close(); err != nil {
		os.Remove(target)
		return err
	}
	if info, statErr := os.Stat(target); statErr != nil || info.Size() == 0 {
		os.Remove(target)
		return fmt.Errorf("compress %s: empty result", path)
	}
	return os.Remove(path)
}
