# TVBalance for Home Assistant

Custom integration for [TVBalance](https://github.com/tvbalance/tvbalance): every TV becomes a Home Assistant
device with status sensors, a Pause button, events for automations, admin-only services and ready-made blueprints.

This repository is a mirror of `ha/custom_components/tvbalance`, published for HACS on each TVBalance release.
Report problems at https://github.com/tvbalance/tvbalance/issues.

## Install

1. In HACS, add this repository as a custom repository (category **Integration**) and download **TVBalance**.
2. Restart Home Assistant.
3. If you run the TVBalance Add-on, a discovery notification appears under **Settings → Devices & services**.
   Otherwise choose **Add integration → TVBalance** and enter the Engine URL and an API token.

The integration needs a running TVBalance Engine (the Add-on, or the Docker image).
