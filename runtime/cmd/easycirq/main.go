package main

import (
	"os"

	"github.com/zsx3896926/EasyCirq/runtime/internal/app"
)

func main() {
	os.Exit(app.Run(os.Args[1:], os.Stdout, os.Stderr))
}
