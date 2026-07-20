#!/usr/bin/env bash
set -euo pipefail

OUT="${1:?usage: monitor_rk3588_rknpu.sh <output_log>}"
INTERVAL="${INTERVAL_SEC:-1}"
APP_PATTERN="${APP_MATCH_PATTERN:-projects/05_alarm_system}"

mkdir -p "$(dirname "${OUT}")"

read_mem_mb() {
  awk '
    /MemTotal:/ {total=$2}
    /MemAvailable:/ {available=$2}
    /SwapTotal:/ {swap_total=$2}
    /SwapFree:/ {swap_free=$2}
    END {
      used=(total-available)/1024;
      swap_used=(swap_total-swap_free)/1024;
      printf "memory_mb=%.1f swap_used_mb=%.1f", used, swap_used
    }
  ' /proc/meminfo
}

read_temp_c() {
  local max_temp=""
  local path value celsius
  for path in /sys/class/thermal/thermal_zone*/temp; do
    [[ -r "${path}" ]] || continue
    value="$(cat "${path}" 2>/dev/null || true)"
    [[ -n "${value}" ]] || continue
    celsius="$(awk -v v="${value}" 'BEGIN { if (v > 1000) printf "%.2f", v / 1000; else printf "%.2f", v }')"
    if [[ -z "${max_temp}" ]]; then
      max_temp="${celsius}"
    else
      max_temp="$(awk -v a="${max_temp}" -v b="${celsius}" 'BEGIN { if (b > a) print b; else print a }')"
    fi
  done
  if [[ -n "${max_temp}" ]]; then
    printf "temperature_c=%s" "${max_temp}"
  else
    printf "temperature_c="
  fi
}

read_rknpu() {
  local path freq load
  freq=""
  load=""
  for path in /sys/class/devfreq/*rknpu*; do
    [[ -d "${path}" ]] || continue
    [[ -r "${path}/cur_freq" ]] && freq="$(cat "${path}/cur_freq" 2>/dev/null || true)"
    [[ -r "${path}/load" ]] && load="$(cat "${path}/load" 2>/dev/null || true)"
    break
  done
  printf "rknpu_cur_freq=%s rknpu_load=%s" "${freq}" "${load}"
}

while true; do
  TS="$(date -Iseconds)"
  LOAD_AVG="$(cat /proc/loadavg)"
  APP_PIDS="$(pgrep -f "${APP_PATTERN}" 2>/dev/null | paste -sd, - || true)"
  printf "%s %s %s %s loadavg=\"%s\" app_pids=\"%s\"\n" \
    "${TS}" "$(read_mem_mb)" "$(read_temp_c)" "$(read_rknpu)" "${LOAD_AVG}" "${APP_PIDS}" >> "${OUT}"
  sleep "${INTERVAL}"
done
