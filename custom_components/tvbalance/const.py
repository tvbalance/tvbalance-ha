"""Constants for the TVBalance integration."""

DOMAIN = "tvbalance"

CONF_URL = "url"
CONF_TOKEN = "token"
CONF_CA_PEM = "ca_pem"  # the Engine's local CA, pinned when the user confirmed its fingerprint

EVENT_NAME = "tvbalance_event"  # fired on the Home Assistant bus for every Engine event
