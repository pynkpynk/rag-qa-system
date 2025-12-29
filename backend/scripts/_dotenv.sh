#!/usr/bin/env bash
set -euo pipefail

dotenv_load_preserve_existing() {
    local env_file="${1:-}"
    if [[ -z "${env_file}" || ! -f "${env_file}" ]]; then
        return 0
    fi
    while IFS= read -r raw_line || [[ -n "${raw_line}" ]]; do
        local line="${raw_line}"
        line="${line%%#*}"
        line="$(echo "${line}" | tr -d '\r')"
        line="$(echo "${line}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
        if [[ -z "${line}" ]]; then
            continue
        fi
        if [[ "${line}" == export* ]]; then
            line="${line#export }"
        fi
        if [[ "${line}" != *"="* ]]; then
            continue
        fi
        local key="${line%%=*}"
        local value="${line#*=}"
        key="$(echo "${key}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
        value="$(echo "${value}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
        if [[ -z "${key}" ]]; then
            continue
        fi
        if [[ "${value}" == "'''" || "${value}" == '"""' ]]; then
            value=""
        elif [[ ${#value} -ge 2 ]]; then
            local first_char="${value:0:1}"
            local last_char="${value: -1}"
            if [[ "${first_char}" == "${last_char}" && ( "${first_char}" == "'" || "${first_char}" == '"' ) ]]; then
                local inner_len=$(( ${#value} - 2 ))
                if [[ ${inner_len} -gt 0 ]]; then
                    value="${value:1:inner_len}"
                else
                    value=""
                fi
            fi
        fi
        if printenv "${key}" >/dev/null 2>&1; then
            continue
        fi
        export "${key}=${value}"
    done < "${env_file}"
}
