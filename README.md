# MX Master 4 Haptics Access

Get haptic feedback on your Logitech MX Master 
## Features

- 🖱️ **HID++ Protocol Support** - Direct communication with Logitech MX Master 4
- 📳 **Haptic Feedback** - Provides tactile alerts
- 🐧 **Desktop Agnostic** - Converted to work with Windows
- 🔧 **Lightweight** - Minimal dependencies and resource usage

## Requirements

- Python 3.12+
- Logitech MX Master 4 mouse (connected via USB receiver or Bluetooth)
- Windows System
- `dbus-monitor` utility (usually pre-installed)



## Usage

run.bat

The script will:

- Automatically detect and connect to your MX Master 4 mouse
- Monitor D-Bus for incoming notifications
- Trigger haptic feedback whenever a button on the program is pressed



## License

MIT
