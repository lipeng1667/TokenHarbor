#!/usr/bin/env bash
# Run only on the authorized Linux test host. Never install this as a boot unit.
# Usage: bash launch.sh /srv/tokenharbor-oes-test/20261105 build|functional
set -euo pipefail
[[ $# == 2 && $EUID == 0 ]] || { echo "Usage (root): $0 STAGE build|functional" >&2; exit 2; }
stage=$(realpath -e -- "$1")
mode=$2
state=/var/lib/tokenharbor-oes-test
[[ -d "$stage/source" && -d "$stage/sysroot" && -d "$stage/harness" ]]
[[ "$stage" != *$'\n'* && "$stage" != *:* ]]
for unit in tokenharbor-oes-build.service tokenharbor-oes-functional.service; do
    if systemctl is-active --quiet "$unit"; then
        echo "A test unit is already running: $unit" >&2
        exit 1
    fi
done
properties=(
    --wait --pipe --collect
    -p DynamicUser=yes -p User=tokenharbor-oes-test
    -p StateDirectory=tokenharbor-oes-test -p StateDirectoryMode=0700
    -p "WorkingDirectory=$state"
    -p PrivateNetwork=yes -p PrivateIPC=yes -p PrivateTmp=yes -p PrivateDevices=yes
    -p ProtectSystem=strict -p ProtectHome=yes -p NoNewPrivileges=yes
    -p CapabilityBoundingSet=
    -p MemoryMax=900M -p MemorySwapMax=0 -p CPUQuota=50% -p TasksMax=96
    -p Nice=10 -p LimitCORE=0 -p LimitNOFILE=4096
)
case "$mode" in
    build)
        systemd-run --unit=tokenharbor-oes-build "${properties[@]}" -p RuntimeMaxSec=900 \
            /usr/bin/env OES_DEFER_RUNTIME_CHECK=1 /bin/bash "$stage/harness/build.sh" \
            "$stage/source" "$stage/sysroot" "$state/build"
        install -d -m 0755 "$stage/bin"
        for name in httpportal okernel dispatcher; do
            install -m 0555 "$state/build/bin/$name" "$stage/bin/$name"
        done
        ;;
    functional)
        link_test_file() {
            local name=$1 target=$2
            if [[ -L "$stage/bin/$name" ]]; then
                [[ $(readlink -- "$stage/bin/$name") == "$target" ]] || {
                    echo "Unexpected existing test link: $name" >&2; exit 1;
                }
            elif [[ -e "$stage/bin/$name" ]]; then
                echo "Refusing to replace existing file: $name" >&2; exit 1
            else
                ln -s -- "$target" "$stage/bin/$name"
            fi
        }
        for name in httpportal okernel; do
            link_test_file "$name.conf" "$state/current/$name/$name.conf"
        done
        for name in order_of_user_0.dat order_of_dispatcher_0.dat order_of_dispatcher_1.dat; do
            link_test_file "$name" "$state/current/okernel/$name"
        done
        link_test_file tmp_notify_data_of_user_0.dat "$state/current/httpportal/tmp_notify_data_of_user_0.dat"
        for day in "$(date +%Y%m%d)" "$(date -d tomorrow +%Y%m%d)"; do
            name="dbupdate_err_${day}.sql"
            link_test_file "$name" "$state/current/okernel/$name"
        done
        systemd-run --unit=tokenharbor-oes-functional "${properties[@]}" -p RuntimeMaxSec=300 \
            /usr/bin/python3 "$stage/harness/run_functional.py" "$stage" "$state"
        ;;
    *) echo "Unknown mode: $mode" >&2; exit 2 ;;
esac
