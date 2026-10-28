package protocol

// WireVersion is the envelope version carried by every request/response frame
// and by the connector handshake. It is part of the EasyCirq connector contract:
// a connector that speaks a different wire version must not be trusted to
// execute writes.
const WireVersion = "v1"

// ServiceName is the loopback service identity the daemon announces in its
// handshake frame. Connectors validate it before registering, which is what
// keeps an upstream easyeda-agent daemon and a EasyCirq daemon from ever being
// mistaken for one another, even when both listen on localhost.
const ServiceName = "easycirq-agent"
