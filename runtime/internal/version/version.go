package version

// Version is overridden at build time via -ldflags for release builds.
var (
	Name    = "easycirq"
	Version = "dev"

	// ConnectorName/Version identify the in-EDA connector build that this
	// runtime ships with. Release builds override both via -ldflags so the CLI
	// and the packaged .eext cannot silently drift apart.
	ConnectorName    = "easycirq-connector"
	ConnectorVersion = "0.1.4"
)
