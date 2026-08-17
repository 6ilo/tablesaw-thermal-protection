#!/usr/bin/env bash
#
# Build, flash and monitor the table saw thermal supervisor from a terminal on macOS.
#
#   ./scripts/flash.sh all          preflight, test, build, flash, then tell you how to
#                                   watch the serial log
#   ./scripts/flash.sh doctor       what is installed, which port, which chip, which flash
#                                   size, which environment it would use
#   ./scripts/flash.sh test         host unit tests only, no board needed
#   ./scripts/flash.sh build        compile only
#   ./scripts/flash.sh flash        compile and upload
#   ./scripts/flash.sh fs           upload the offline error-code bundle to LittleFS
#   ./scripts/flash.sh monitor      serial log
#   ./scripts/flash.sh logs         pull the long-term CSV log off the running board
#   ./scripts/flash.sh clean        drop build artifacts
#
# Options:
#   --env <name>    path_a | path_a_8mb | path_b | path_b_8mb   (default: auto by flash size)
#   --port <dev>    serial device (default: auto-detected)
#   --trip <C>      override SAW_TRIP_C for this build, for commissioning
#   --warn <C>      override SAW_WARN_C
#   --reset <C>     override SAW_RESET_C
#   --yes           do not ask for confirmation before writing to the board
#
# SAFETY. Flashing drives the board through a reset, and during the upload the ESP32's
# GPIOs are inputs. The 10 kOhm pulldown on GPIO26 required by WIRING.md is what makes
# that safe: floating means not-transmitting means the contactor coil circuit is open.
#
#   If that pulldown is not fitted, do not flash with mains connected. Lock out the
#   machine disconnect first.
#
# Even with the pulldown fitted, the supervisor cannot protect anything while it is being
# flashed, so the saw must not be in use.

set -euo pipefail

FW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="$(cd "$FW_DIR/.." && pwd)"
cd "$FW_DIR"

ENV_NAME=""
PORT=""
ASSUME_YES=0
EXTRA_FLAGS=()

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }
warn() { printf '\033[33m  ! %s\033[0m\n' "$*"; }
die()  { printf '\033[31merror: %s\033[0m\n' "$*" >&2; exit 1; }

# --------------------------------------------------------------------------- #
# argument parsing
# --------------------------------------------------------------------------- #

CMD="${1:-all}"
shift || true

while [ $# -gt 0 ]; do
    case "$1" in
        --env)   ENV_NAME="${2:-}"; shift 2 ;;
        --port)  PORT="${2:-}"; shift 2 ;;
        --trip)  EXTRA_FLAGS+=("-DSAW_TRIP_C=${2:-}"); shift 2 ;;
        --warn)  EXTRA_FLAGS+=("-DSAW_WARN_C=${2:-}"); shift 2 ;;
        --reset) EXTRA_FLAGS+=("-DSAW_RESET_C=${2:-}"); shift 2 ;;
        --yes|-y) ASSUME_YES=1; shift ;;
        *) die "unknown option: $1" ;;
    esac
done

# --------------------------------------------------------------------------- #
# platformio
# --------------------------------------------------------------------------- #

find_pio() {
    for candidate in pio platformio "$HOME/.platformio/penv/bin/pio"; do
        if command -v "$candidate" >/dev/null 2>&1; then
            command -v "$candidate"
            return 0
        fi
        if [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

ensure_pio() {
    if PIO="$(find_pio)"; then
        return 0
    fi

    bold "PlatformIO is not installed. Installing it."
    if command -v brew >/dev/null 2>&1; then
        # pipx keeps PlatformIO and its own Python out of the system site-packages, which
        # is what Homebrew's externally-managed Python requires anyway.
        brew list pipx >/dev/null 2>&1 || brew install pipx
        pipx ensurepath >/dev/null 2>&1 || true
        pipx install platformio
    elif command -v python3 >/dev/null 2>&1; then
        python3 -m pip install --user platformio
    else
        die "no Homebrew and no python3. Install Homebrew from https://brew.sh first."
    fi

    export PATH="$HOME/.local/bin:$PATH"
    PIO="$(find_pio)" || die "PlatformIO installed but is not on PATH. Open a new terminal and retry."
}

# --------------------------------------------------------------------------- #
# port and chip discovery
# --------------------------------------------------------------------------- #

list_ports() {
    # cu.* rather than tty.* on macOS: opening tty.* blocks waiting for carrier detect.
    /bin/ls /dev/cu.usbserial* /dev/cu.usbmodem* /dev/cu.SLAB_USBtoUART* \
            /dev/cu.wchusbserial* 2>/dev/null || true
}

detect_port() {
    if [ -n "$PORT" ]; then
        echo "$PORT"
        return 0
    fi

    local found
    found="$(list_ports)"
    local count
    count="$(printf '%s\n' "$found" | grep -c . || true)"

    if [ "$count" -eq 0 ]; then
        return 1
    fi
    if [ "$count" -gt 1 ]; then
        warn "more than one serial device present:" >&2
        printf '%s\n' "$found" | sed 's/^/      /' >&2
        warn "using the first; pass --port to choose" >&2
    fi
    printf '%s\n' "$found" | head -1
}

no_port_help() {
    cat <<'EOF'
No ESP32 serial port found.

  1. Is the board plugged in? Use a data USB-C cable, not a charge-only one.
  2. Compare before and after plugging it in:  ls /dev/cu.*
  3. If nothing new appears, macOS has no driver for the board's USB-UART chip.
     Identify it:   system_profiler SPUSBDataType | grep -iE 'cp210|ch34|ch9102|ftdi|serial'
     Then install the matching driver:
        Silicon Labs CP210x   brew install --cask silicon-labs-vcp-driver
        WCH CH34x / CH9102    brew install --cask wch-ch34x-usb-serial-driver
        FTDI                  usually works with no driver on current macOS
     A driver install needs a reboot and an approval in
     System Settings > Privacy & Security.
  4. Some boards need BOOT held while you plug in to enter download mode.
EOF
}

# Prints the flash size in MB, or nothing if it cannot be read.
detect_flash_size() {
    local port="$1" out=""
    for runner in \
        "$PIO pkg exec -p tool-esptoolpy -- esptool.py" \
        "$PIO pkg exec -p tool-esptoolpy -- esptool" \
        "python3 -m esptool"
    do
        # shellcheck disable=SC2086
        out="$($runner --chip esp32 --port "$port" --no-stub flash_id 2>/dev/null || true)"
        if printf '%s' "$out" | grep -qi 'flash size'; then
            printf '%s' "$out" | grep -i 'flash size' | grep -oE '[0-9]+MB' | head -1 \
                | tr -d 'MB'
            return 0
        fi
    done
    return 1
}

# --------------------------------------------------------------------------- #
# environment selection
# --------------------------------------------------------------------------- #

# Path A unless the caller says otherwise: it is the build the project's hardware
# actually exists for. Path B needs the MAX31855, the wired relay and the thermostat,
# none of which the BOM records as purchased.
BASE_PATH="${SAW_PATH:-a}"

resolve_env() {
    if [ -n "$ENV_NAME" ]; then
        echo "$ENV_NAME"
        return 0
    fi

    local size="" port
    if port="$(detect_port 2>/dev/null)"; then
        size="$(detect_flash_size "$port" || true)"
    fi

    # 4 MB layout unless 8 MB is positively confirmed. An 8 MB partition table on a 4 MB
    # part produces a board that does not boot, and the 4 MB table works on both.
    if [ "$size" = "8" ]; then
        echo "path_${BASE_PATH}_8mb"
    else
        echo "path_${BASE_PATH}"
    fi
}

confirm() {
    [ "$ASSUME_YES" -eq 1 ] && return 0
    printf '\n'
    bold "About to write firmware to the board."
    info "The supervisor cannot protect the saw while it is being flashed."
    info "GPIO26 must have its 10 kOhm pulldown fitted, or the machine disconnect"
    info "must be locked out. See WIRING.md."
    printf '\n  Continue? [y/N] '
    read -r reply
    case "$reply" in [yY]*) return 0 ;; *) die "cancelled" ;; esac
}

run_pio() {
    local env_name="$1"
    shift

    # Threshold overrides ride in through ${sysenv.SAW_EXTRA_FLAGS}, which platformio.ini
    # interpolates into every environment's build_flags. Every constant in saw_config.h is
    # #ifndef-guarded, so a -D here wins over the tracked default without editing source
    # and without disturbing -DSAW_PATH_A.
    if [ "${#EXTRA_FLAGS[@]}" -gt 0 ]; then
        SAW_EXTRA_FLAGS="${EXTRA_FLAGS[*]}"
        export SAW_EXTRA_FLAGS
        warn "threshold override in effect: $SAW_EXTRA_FLAGS"
        warn "this binary will not match the tracked source. Record it in the commissioning log."
    fi

    "$PIO" run -e "$env_name" "$@"
}

# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

cmd_doctor() {
    bold "toolchain"
    info "platformio   $("$PIO" --version 2>/dev/null || echo 'MISSING')"
    info "python3      $(python3 --version 2>&1 || echo 'MISSING')"
    info "homebrew     $(brew --version 2>/dev/null | head -1 || echo 'not installed')"

    bold "board"
    local port
    if port="$(detect_port)"; then
        info "port         $port"
        local size
        if size="$(detect_flash_size "$port")"; then
            info "flash        ${size} MB (read from the chip)"
        else
            warn "flash size could not be read — assuming 4 MB, which is safe on both"
        fi
    else
        warn "no serial port found"
        no_port_help
    fi

    bold "build"
    info "environment  $(resolve_env)"
    info "generated    $([ -f generated/error_codes.h ] && echo 'generated/error_codes.h present' || echo 'MISSING — run tools/codedocs.py build')"

    bold "safety reminders"
    info "GPIO26 needs a 10 kOhm pulldown to GND. Measure it."
    info "With the board unpowered, the receiver contact must be open."
    info "Two-point calibration must be done before the probe goes on the motor."
    info "Set SAW_CALIBRATED to 1 in include/saw_calibration.h once it has been."
}

cmd_test() {
    bold "host unit tests (no board required)"
    "$PIO" test -e native
}

cmd_build() {
    local env_name
    env_name="$(resolve_env)"
    bold "building $env_name"
    run_pio "$env_name"
}

cmd_flash() {
    local env_name port
    env_name="$(resolve_env)"
    port="$(detect_port)" || { no_port_help; die "no serial port"; }

    bold "flashing $env_name to $port"
    confirm
    run_pio "$env_name" -t upload --upload-port "$port"

    printf '\n'
    bold "flashed."
    info "watch the boot banner and the self-test:  ./scripts/flash.sh monitor"
    info "dashboard: join the \"ALN Table Saw\" Wi-Fi network, then http://saw.local/"
}

cmd_fs() {
    local env_name port
    env_name="$(resolve_env)"
    port="$(detect_port)" || { no_port_help; die "no serial port"; }

    # The offline operator pages are built from docs/codes/ by the repo's own tool. They
    # are optional: without them the dashboard links to GitHub instead.
    if [ ! -d "$REPO_DIR/build/site" ]; then
        bold "building the error-code bundle"
        (cd "$REPO_DIR" && python3 -m pip install -q -r tools/requirements.txt \
            && python3 tools/codedocs.py build) \
            || die "could not build the bundle; see tools/README or run codedocs.py by hand"
    fi

    mkdir -p data/codes
    cp "$REPO_DIR"/build/site/*.html.gz data/codes/ 2>/dev/null || true
    cp "$REPO_DIR"/build/site/manifest.json data/codes/ 2>/dev/null || true
    # The device serves index.html; the gzip copy is what it actually sends.
    info "staged $(/bin/ls -1 data/codes | wc -l | tr -d ' ') files into data/codes/"

    bold "uploading the filesystem image to $port"
    confirm
    "$PIO" run -e "$env_name" -t uploadfs --upload-port "$port"
}

cmd_monitor() {
    local port
    port="$(detect_port)" || { no_port_help; die "no serial port"; }
    bold "serial monitor on $port — ctrl-] to quit"
    "$PIO" device monitor --port "$port" --baud 115200
}

cmd_logs() {
    local out="${SAW_LOG_OUT:-saw-log.csv}"
    bold "pulling the long-term log off the board"
    info "this needs your Mac joined to the \"ALN Table Saw\" network"
    curl -fsS --max-time 120 "http://saw.local/api/log.csv" -o "$out" \
        || curl -fsS --max-time 120 "http://192.168.4.1/api/log.csv" -o "$out" \
        || die "could not reach the board. Join its Wi-Fi network and retry."
    info "wrote $out ($(wc -l < "$out" | tr -d ' ') lines)"
}

cmd_clean() {
    bold "cleaning"
    "$PIO" run -t clean 2>/dev/null || true
    rm -rf .pio data/codes
}

cmd_all() {
    cmd_doctor
    printf '\n'
    cmd_test
    printf '\n'
    cmd_flash
}

ensure_pio
PIO="${PIO:-$(find_pio)}"

case "$CMD" in
    doctor)  cmd_doctor ;;
    port)    detect_port || { no_port_help; exit 1; } ;;
    test)    cmd_test ;;
    build)   cmd_build ;;
    flash|upload) cmd_flash ;;
    fs|uploadfs)  cmd_fs ;;
    monitor) cmd_monitor ;;
    logs)    cmd_logs ;;
    clean)   cmd_clean ;;
    all)     cmd_all ;;
    *)       die "unknown command: $CMD (try: all, doctor, test, build, flash, fs, monitor, logs, clean)" ;;
esac
